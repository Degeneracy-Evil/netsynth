"""Endpoint-only reliable unordered Messages; deterministic semantic, not wire, model."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from secrets import token_bytes
from typing import Literal
from zlib import crc32

from netsynth.scale4 import RouteProgram
from netsynth.scale5 import EndpointBinding, EndpointID

HEADER_BYTES = 64  # Model accounting only: no wire layout is specified.


@dataclass(frozen=True)
class ReceiveToken:
    """Opaque receiver-local identifier, with no forwarding meaning."""

    value: bytes


@dataclass(frozen=True)
class Fragment:
    message_id: int
    total_size: int
    offset: int
    payload: bytes


@dataclass(frozen=True)
class Feedback:
    """Packet receipts and cumulative receive limit are independent fields."""

    receipts: tuple[tuple[int, bool], ...]
    credit_limit: int


type Frame = Fragment | Feedback


@dataclass(frozen=True)
class ChannelPacket:
    source_eid: EndpointID
    destination_eid: EndpointID
    receive_token: ReceiveToken
    packet_number: int
    frame: Frame
    checksum: int

    @classmethod
    def create(
        cls, source: EndpointID, destination: EndpointID, token: ReceiveToken, number: int, frame: Frame
    ) -> ChannelPacket:
        packet = cls(source, destination, token, number, frame, 0)
        return cls(source, destination, token, number, frame, packet.expected_checksum())

    def expected_checksum(self) -> int:
        """CRC detects accidental corruption, NOT authentication; repr is not a wire format."""
        return crc32(
            repr((self.source_eid, self.destination_eid, self.receive_token, self.packet_number, self.frame)).encode()
        )

    @property
    def size(self) -> int:
        return HEADER_BYTES + (len(self.frame.payload) if isinstance(self.frame, Fragment) else 0)


@dataclass
class PathState:
    epoch: int
    binding: EndpointBinding
    program: RouteProgram
    pmtu: int
    congestion_window: int
    bytes_in_flight: int = 0
    rtt: float | None = None
    rtt_variance: float | None = None
    congestion_marks: int = 0
    losses: int = 0
    confirmed: bool = False
    next_send_tick: int = 0
    retired_at: int | None = None


@dataclass
class SentPacket:
    packet: ChannelPacket
    path_epoch: int
    send_tick: int
    in_flight: bool = True
    acknowledged: bool = False
    marked: bool = False


@dataclass
class _SendingMessage:
    payload: bytes
    acknowledged: set[int] = field(default_factory=set)
    transmitted: set[int] = field(default_factory=set)
    empty_sent: bool = False
    empty_acked: bool = False


@dataclass
class _Reassembly:
    total_size: int
    data: dict[int, int] = field(default_factory=dict)


class Channel:
    """One endpoint's full-duplex Channel half; the peer owns the reverse half."""

    def __init__(
        self,
        local_eid: EndpointID,
        remote_eid: EndpointID,
        local_token: ReceiveToken,
        remote_token: ReceiveToken,
        maximum_message_size: int,
        receive_capacity: int,
        peer_capacity: int,
    ) -> None:
        if maximum_message_size < 1 or min(receive_capacity, peer_capacity) < maximum_message_size:
            raise ValueError("finite positive message limit must fit both receiver capacities")
        self.local_eid, self.remote_eid = local_eid, remote_eid
        self.local_receive_token, self.remote_receive_token = local_token, remote_token
        self.maximum_message_size = maximum_message_size
        self.receive_capacity = receive_capacity
        self.local_credit_limit = receive_capacity
        self.peer_credit_limit = peer_capacity
        self.committed_send_bytes = 0
        self.committed_receive_bytes = 0
        self.buffered_bytes = 0
        self.next_packet_number = 0
        self.next_message_id = 0
        self.messages: dict[int, _SendingMessage] = {}
        self.reassembly: dict[int, _Reassembly] = {}
        self.completed: dict[int, bytes] = {}
        self.delivery_order: list[int] = []
        # Retain checksum identity, not old fragment payloads after upper-layer consumption.
        self.received_packets: dict[int, int] = {}
        self.receipts: dict[int, bool] = {}
        self.sent_packets: dict[int, SentPacket] = {}
        self.paths: dict[int, PathState] = {}
        self.active_epoch: int | None = None
        self._next_epoch = 0
        self._binding: EndpointBinding | None = None
        self.closed = False
        self._consumed: set[int] = set()

    @property
    def active_path(self) -> PathState:
        if self.active_epoch is None:
            raise ValueError("no active path")
        return self.paths[self.active_epoch]

    def replace_path(self, binding: EndpointBinding, program: RouteProgram, pmtu: int, now: int) -> PathState:
        if self.closed or binding.eid != self.remote_eid or program.destination not in binding.locators:
            raise ValueError("path must address this live Channel's remote EID binding")
        if pmtu <= HEADER_BYTES or now < 0:
            raise ValueError("path needs positive payload budget and time")
        if self._binding is not None and (
            binding.version < self._binding.version
            or (binding.version == self._binding.version and binding != self._binding)
        ):
            raise ValueError("path binding cannot regress or conflict")
        if self.active_epoch is not None:
            self.active_path.retired_at = now
        path = PathState(self._next_epoch, binding, program, pmtu, 2 * pmtu)
        self.paths[path.epoch] = path
        self.active_epoch = path.epoch
        self._next_epoch += 1
        self._binding = binding
        return path

    def retire_path(self, epoch: int, now: int, retention_ticks: int = 10) -> None:
        path = self.paths[epoch]
        if (
            epoch == self.active_epoch
            or path.retired_at is None
            or retention_ticks < 0
            or now < path.retired_at + retention_ticks
            or any(record.in_flight and record.path_epoch == epoch for record in self.sent_packets.values())
        ):
            raise ValueError("old path still active, outstanding, or within retention window")
        del self.paths[epoch]

    def queue_message(self, payload: bytes) -> int:
        charge = max(1, len(payload))
        if self.closed or len(payload) > self.maximum_message_size:
            raise ValueError("closed Channel or Message exceeds negotiated finite limit")
        if self.committed_send_bytes + charge > self.peer_credit_limit:
            raise ValueError("receiver flow credit exhausted")
        message_id = self.next_message_id
        self.next_message_id += 1
        self.committed_send_bytes += charge
        self.messages[message_id] = _SendingMessage(payload)
        return message_id

    def _packet(self, frame: Frame) -> ChannelPacket:
        if self.closed:
            raise ValueError("Channel closed")
        packet = ChannelPacket.create(
            self.local_eid, self.remote_eid, self.remote_receive_token, self.next_packet_number, frame
        )
        self.next_packet_number += 1
        return packet

    def send_next(self, now: int) -> ChannelPacket | None:
        """One fragment per paced event; re-packetize unsatisfied ranges on the active path."""
        path = self.active_path
        if self.closed or now < path.next_send_tick:
            return None
        for message_id, message in self.messages.items():
            missing = set(range(len(message.payload))) - message.acknowledged - message.transmitted
            if not missing and (message.payload or message.empty_sent or message.empty_acked):
                continue
            offset = min(missing) if missing else 0
            end = offset
            while end in missing and end - offset < path.pmtu - HEADER_BYTES:
                end += 1
            fragment = Fragment(message_id, len(message.payload), offset, message.payload[offset:end])
            size = HEADER_BYTES + len(fragment.payload)
            if path.bytes_in_flight + size > path.congestion_window:
                return None
            packet = self._packet(fragment)
            self.sent_packets[packet.packet_number] = SentPacket(packet, path.epoch, now)
            message.transmitted.update(range(offset, end))
            message.empty_sent = True
            path.bytes_in_flight += packet.size
            path.next_send_tick = now + 1
            return packet
        return None

    def mark_lost(self, number: int) -> None:
        """Explicit deterministic loss event, not a production loss detector."""
        record = self.sent_packets[number]
        if not record.in_flight:
            return
        record.in_flight = False
        path = self.paths.get(record.path_epoch)
        if path is not None:
            path.bytes_in_flight -= record.packet.size
            path.losses += 1
            path.congestion_window = max(path.pmtu, path.congestion_window // 2)
        fragment = record.packet.frame
        if isinstance(fragment, Fragment):
            message = self.messages[fragment.message_id]
            message.transmitted.difference_update(range(fragment.offset, fragment.offset + len(fragment.payload)))
            message.empty_sent = False

    def make_feedback(self) -> ChannelPacket:
        """Repeat cumulative receipts/credit explicitly; ACK-only packets do not elicit ACKs."""
        return self._packet(Feedback(tuple(sorted(self.receipts.items())), self.local_credit_limit))

    def _validate(self, packet: ChannelPacket) -> bool:
        if (
            packet.packet_number < 0
            or packet.source_eid != self.remote_eid
            or packet.destination_eid != self.local_eid
            or packet.receive_token != self.local_receive_token
        ):
            return False
        prior = self.received_packets.get(packet.packet_number)
        if prior is not None:
            return prior == packet.checksum
        frame = packet.frame
        if isinstance(frame, Feedback):
            return frame.credit_limit >= 0 and all(
                0 <= number < self.next_packet_number for number, _ in frame.receipts
            )
        if (
            frame.message_id < 0
            or not 0 <= frame.total_size <= self.maximum_message_size
            or frame.offset < 0
            or frame.offset + len(frame.payload) > frame.total_size
            or (frame.total_size > 0 and not frame.payload)
        ):
            return False
        assembled = self.reassembly.get(frame.message_id)
        if frame.message_id in self.completed:
            # Retain size after consumption; a completed ID cannot redeliver.
            return (
                assembled is not None
                and assembled.total_size == frame.total_size
                and all(
                    assembled.data.get(frame.offset + index, byte) == byte for index, byte in enumerate(frame.payload)
                )
            )
        if assembled is None:
            charge = max(1, frame.total_size)
            return (
                self.committed_receive_bytes + charge <= self.local_credit_limit
                and self.buffered_bytes + charge <= self.receive_capacity
            )
        return assembled.total_size == frame.total_size and all(
            assembled.data.get(frame.offset + index, byte) == byte for index, byte in enumerate(frame.payload)
        )

    def receive(
        self, packet: ChannelPacket, now: int, congestion_mark: bool = False
    ) -> Literal["accepted", "duplicate", "corrupt", "invalid", "closed"]:
        """Integrity and structural checks precede ALL Channel mutation."""
        if packet.checksum != packet.expected_checksum():
            return "corrupt"
        if self.closed:
            return "closed"
        if now < 0 or not self._validate(packet):
            return "invalid"
        if packet.packet_number in self.received_packets:
            if isinstance(packet.frame, Fragment):
                self.receipts[packet.packet_number] |= congestion_mark
            return "duplicate"
        self.received_packets[packet.packet_number] = packet.checksum
        frame = packet.frame
        if isinstance(frame, Feedback):
            self.peer_credit_limit = max(self.peer_credit_limit, frame.credit_limit)
            for number, marked in frame.receipts:
                self._acknowledge(number, marked, now)
        else:
            self.receipts[packet.packet_number] = congestion_mark
            if frame.message_id not in self.completed:
                assembled = self.reassembly.get(frame.message_id)
                if assembled is None:
                    assembled = _Reassembly(frame.total_size)
                    self.reassembly[frame.message_id] = assembled
                    charge = max(1, frame.total_size)
                    self.committed_receive_bytes += charge
                    self.buffered_bytes += charge
                assembled.data.update((frame.offset + index, byte) for index, byte in enumerate(frame.payload))
                if len(assembled.data) == assembled.total_size:
                    self.completed[frame.message_id] = bytes(assembled.data[index] for index in range(frame.total_size))
                    self.delivery_order.append(frame.message_id)
        return "accepted"

    def _acknowledge(self, number: int, marked: bool, now: int) -> None:
        record = self.sent_packets.get(number)
        if record is None:
            return  # ACK-only PN, or history outside this model's sent-data records.
        path = self.paths.get(record.path_epoch)
        if not record.acknowledged:
            record.acknowledged = True
            if path is not None:
                if record.in_flight:
                    path.bytes_in_flight -= record.packet.size
                sample = float(max(0, now - record.send_tick))
                old_rtt = path.rtt
                path.rtt = sample if old_rtt is None else 0.875 * old_rtt + 0.125 * sample
                path.rtt_variance = (
                    sample / 2 if old_rtt is None else 0.75 * (path.rtt_variance or 0) + 0.25 * abs(old_rtt - sample)
                )
                path.confirmed = True
                path.congestion_window += 1  # Deliberately tiny toy response, not an algorithm benchmark.
            record.in_flight = False
            fragment = record.packet.frame
            if isinstance(fragment, Fragment):
                message = self.messages[fragment.message_id]
                message.acknowledged.update(range(fragment.offset, fragment.offset + len(fragment.payload)))
                message.empty_acked = True
        if marked and not record.marked:
            record.marked = True
            if path is not None:
                path.congestion_marks += 1
                path.congestion_window = max(path.pmtu, path.congestion_window // 2)

    def consume_message(self, message_id: int) -> bytes:
        """Upper-layer consumption, not ACK, releases reserved receive memory."""
        payload = self.completed[message_id]
        assembled = self.reassembly[message_id]
        if message_id in self._consumed:
            raise ValueError("Message already consumed")
        assembled.data.clear()
        self.completed[message_id] = b""  # Completion tombstone, not application data.
        self._consumed.add(message_id)
        charge = max(1, assembled.total_size)
        self.buffered_bytes -= charge
        self.local_credit_limit += charge
        return payload


@dataclass(frozen=True)
class ChannelEnvelope:
    """Transit may only set the soft mark; it need not parse the transport payload."""

    packet: ChannelPacket
    congestion_mark: bool = False

    def mark_congestion(self) -> ChannelEnvelope:
        return ChannelEnvelope(self.packet, True)


class EndpointChannels:
    """Local token table owned by the exact Scale-5 Endpoint, never by a router."""

    def __init__(self, eid: EndpointID, entropy: Callable[[], bytes] | None = None) -> None:
        self.eid = eid
        self.channels: dict[ReceiveToken, Channel] = {}
        self._entropy = entropy if entropy is not None else lambda: token_bytes(16)
        self._next_token = 0

    def _allocate_token(self) -> ReceiveToken:
        # Entropy is injectable for reproducible tests. Counter prevents intentional reuse,
        # including after close, without a growing retired-token tombstone table.
        entropy = self._entropy()
        if len(entropy) != 16:
            raise ValueError("prototype token entropy must be 16 bytes")
        token = ReceiveToken(entropy + self._next_token.to_bytes(16))
        self._next_token += 1
        return token

    def close(self, token: ReceiveToken) -> None:
        channel = self.channels.pop(token)
        channel.closed = True

    def receive(self, envelope: ChannelEnvelope, now: int) -> str:
        packet = envelope.packet
        if packet.checksum != packet.expected_checksum():
            return "corrupt"
        if packet.destination_eid != self.eid:
            return "wrong_eid"
        channel = self.channels.get(packet.receive_token)
        if channel is None:
            return "unknown_token"
        return channel.receive(packet, now, envelope.congestion_mark)


def establish_channel(
    left: EndpointChannels,
    right: EndpointChannels,
    maximum_message_size: int = 64,
    left_capacity: int = 64,
    right_capacity: int = 64,
) -> tuple[Channel, Channel]:
    """Tiny successful OPEN/ACCEPT exchange model; no RPC, retry timer, or wire encoding.

    Endpoint-local token exchange and finite resource agreement only. Opening authentication,
    replay/retry policy and crash/restart semantics are deliberately not modeled.
    """
    if maximum_message_size < 1 or min(left_capacity, right_capacity) < maximum_message_size:
        raise ValueError("negotiated Message size must fit both endpoint capacities")
    left_token, right_token = left._allocate_token(), right._allocate_token()
    a = Channel(left.eid, right.eid, left_token, right_token, maximum_message_size, left_capacity, right_capacity)
    b = Channel(right.eid, left.eid, right_token, left_token, maximum_message_size, right_capacity, left_capacity)
    left.channels[left_token], right.channels[right_token] = a, b
    return a, b
