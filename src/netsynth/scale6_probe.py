"""Tiny deterministic loss/reorder/migration/corruption workload, no performance sweep."""

from __future__ import annotations

from dataclasses import replace
from types import MappingProxyType

from netsynth.forwarding import Locator
from netsynth.scale4 import (
    AccessHandle,
    AccessRealization,
    AccessRegistry,
    DestinationAccessOffer,
    PhysicalHop,
    RouteProgram,
    RouteQueryContext,
    SourceAccessOffer,
)
from netsynth.scale5 import (
    BindingResolver,
    BindingService,
    Endpoint,
    EndpointID,
    EndpointPacket,
    LocalAttachment,
    deliver_endpoint_packet,
)
from netsynth.scale5_probe import TinyAttachmentFixture
from netsynth.scale5_probe import run_probe as scale5_probe
from netsynth.scale6 import Channel, ChannelEnvelope, ChannelPacket, EndpointChannels, establish_channel


class TinyChannelFixture(TinyAttachmentFixture):
    """Extend only fixture access construction, not frozen Scale-4/5 routing."""

    def __init__(self) -> None:
        super().__init__()
        self.local_locator = Locator((0,), 0)
        self.local = Endpoint(EndpointID(b"left"))
        self.remote = Endpoint(EndpointID(b"right"))
        self.local_attachment = LocalAttachment(self.local_locator, 0)
        self.old_attachment = LocalAttachment(self.old_locator, 3)
        self.new_attachment = LocalAttachment(self.new_locator, 4)
        self.local_attachment.attach(self.local)
        self.old_attachment.attach(self.remote)
        self.left = EndpointChannels(self.local.eid, lambda: b"A" * 16)
        self.right = EndpointChannels(self.remote.eid, lambda: b"B" * 16)
        self.a, self.b = establish_channel(self.left, self.right, maximum_message_size=16, right_capacity=16)
        self.binding_service = BindingService((self.old_locator,))
        self.resolver = BindingResolver(self.local_locator, self.binding_service)
        self.initial = self.binding_service.publish(self.remote.eid, frozenset({self.old_locator}))
        self.resolver.resolve(self.remote.eid)
        self.local_binding = self.binding_service.publish(self.local.eid, frozenset({self.local_locator}))
        program, access, context = self.compile_attachment(self.old_locator, "initial")
        self.a.replace_path(self.initial, program, 68, 0)
        self.forward_access, self.forward_context = access, context
        program, access, context = self.compile_reverse(False, "reverse")
        self.b.replace_path(self.local_binding, program, 68, 0)
        self.reverse_access, self.reverse_context = access, context
        self.forward_history = {
            self.a.active_path.epoch: (self.forward_access, self.forward_context, self.old_attachment)
        }
        self.reverse_history = {
            self.b.active_path.epoch: (self.reverse_access, self.reverse_context, self.local_attachment)
        }

    def compile_reverse(
        self, moved: bool, query_id: str
    ) -> tuple[RouteProgram, MappingProxyType[str, AccessRegistry], RouteQueryContext]:
        source = 4 if moved else 3
        actions = (PhysicalHop(4, 3),) if moved else ()
        source_offer = SourceAccessOffer(3, float(len(actions)), AccessHandle("target", query_id, 0))
        target_offer = DestinationAccessOffer(0, 0.0, AccessHandle("source", query_id, 0))
        source_access = AccessRegistry("target", query_id, frozenset({3}), frozenset({PhysicalHop(4, 3)}))
        source_access.publish_source(source_offer, AccessRealization(source, 3, actions))
        target_access = AccessRegistry(
            "source", query_id, frozenset({0}), frozenset(), destination=self.local_locator, destination_node=0
        )
        target_access.publish_destination(target_offer, AccessRealization(0, 0, ()))
        compiled = self.service.compile(query_id, self.local_locator, (source_offer,), (target_offer,))
        if compiled is None:
            raise AssertionError("fixture reverse path must exist")
        return (
            compiled.program,
            MappingProxyType({"target": source_access, "source": target_access}),
            RouteQueryContext(query_id, source),
        )

    def transmit(self, packet: ChannelPacket, now: int, marked: bool = False, defer_transport: bool = False) -> str:
        """Route opaque bytes, exact-EID deliver, then dispatch transport at that Endpoint.

        Packet objects stand in for an endpoint codec (no wire format is frozen).
        Neither Scale-4 executor nor Scale-5 local delivery inspects transport fields.
        """
        if packet.destination_eid == self.remote.eid:
            sender, receiver = self.a, self.right
            history = self.forward_history
        else:
            sender, receiver = self.b, self.left
            history = self.reverse_history
        record = sender.sent_packets.get(packet.packet_number)
        epoch = record.path_epoch if record is not None else sender.active_path.epoch
        access, context, attachment = history[epoch]
        program = sender.paths[epoch].program
        result = deliver_endpoint_packet(
            self.graph,
            self.registries,
            access,
            context,
            10,
            EndpointPacket(packet.destination_eid, program.destination, program, repr(packet).encode()),
            attachment,
        )
        if result.status != "delivered":
            return result.status
        if defer_transport:
            return "delivered"  # Already reached the correct Endpoint; process later.
        envelope = ChannelEnvelope(packet)
        if marked:
            envelope = envelope.mark_congestion()
        return receiver.receive(envelope, now)

    def move(self, now: int) -> tuple[str, int]:
        self.old_attachment.detach(self.remote.eid)
        self.old_attachment.attach(Endpoint(EndpointID(b"replacement")))
        self.new_attachment.attach(self.remote)
        current = self.binding_service.publish(self.remote.eid, frozenset({self.new_locator}))
        assert self.resolver.resolve(self.remote.eid) == self.initial
        stale_packet = self.a.make_feedback()
        stale_result = self.transmit(stale_packet, now)
        fresh = self.resolver.resolve_fresh(self.remote.eid, self.initial.version)
        assert fresh == current
        program, self.forward_access, self.forward_context = self.compile_attachment(self.new_locator, "moved")
        self.a.replace_path(fresh, program, 66, now)
        self.forward_history[self.a.active_path.epoch] = (
            self.forward_access,
            self.forward_context,
            self.new_attachment,
        )
        program, self.reverse_access, self.reverse_context = self.compile_reverse(True, "reverse-moved")
        self.b.replace_path(self.local_binding, program, 80, now)
        self.reverse_history[self.b.active_path.epoch] = (
            self.reverse_access,
            self.reverse_context,
            self.local_attachment,
        )
        return stale_result, fresh.version


def require_packet(channel: Channel, now: int) -> ChannelPacket:
    packet = channel.send_next(now)
    if packet is None:
        raise AssertionError("workload expected a paced, credit/congestion-eligible fragment")
    return packet


def run_probe() -> dict[str, object]:
    fixture = TinyChannelFixture()
    a, b = fixture.a, fixture.b
    before = fixture.routing_snapshot()
    m1 = a.queue_message(b"abcdefgh")
    lost = require_packet(a, 0)
    second = require_packet(a, 1)
    assert fixture.transmit(second, 2) == "accepted"
    assert fixture.transmit(second, 3) == "duplicate"
    assert fixture.transmit(b.make_feedback(), 4) == "accepted"
    m2 = a.queue_message(b"XYZ")
    third = require_packet(a, 5)
    assert fixture.transmit(third, 6, marked=True) == "accepted"
    delivered_early = b.delivery_order == [m2] and b.buffered_bytes == 11
    old_feedback = b.make_feedback()
    corrupt = replace(old_feedback, packet_number=999)
    snapshot = repr(vars(a))
    corrupt_status = fixture.transmit(corrupt, 7)
    unchanged_by_corruption = repr(vars(a)) == snapshot
    credit_before = (a.peer_credit_limit, a.committed_send_bytes, b.local_credit_limit, b.buffered_bytes)
    # A delayed original has reached the old Endpoint before it moves, but transport
    # processing is delayed. Do not silently route an old transmission on the new path.
    assert fixture.transmit(lost, 7, defer_transport=True) == "delivered"
    old_path = a.active_path
    stale_status, binding_version = fixture.move(8)
    new_path = a.active_path
    conservative = new_path.rtt is None and new_path.rtt_variance is None and not new_path.confirmed
    independent_pmtu = old_path.pmtu == 68 and new_path.pmtu == 66
    new_snapshot = repr(new_path)
    assert fixture.transmit(old_feedback, 9) == "accepted"
    late_ack_isolated = repr(new_path) == new_snapshot
    marks_attributed = old_path.congestion_marks == 1 and new_path.congestion_marks == 0
    credit_preserved = credit_before == (
        a.peer_credit_limit,
        a.committed_send_bytes,
        b.local_credit_limit,
        b.buffered_bytes,
    )
    a.mark_lost(lost.packet_number)
    retransmission = require_packet(a, 10)
    assert fixture.transmit(retransmission, 11) == "accepted"
    assert fixture.transmit(b.make_feedback(), 12) == "accepted"
    remainder = require_packet(a, 13)
    assert fixture.transmit(remainder, 14) == "accepted"
    assert fixture.transmit(remainder, 15) == "duplicate"
    # Late original packet also contains already completed bytes; cannot redeliver.
    assert fixture.right.receive(ChannelEnvelope(lost).mark_congestion(), 16) == "accepted"
    assert fixture.transmit(b.make_feedback(), 17) == "accepted"
    all_acked = a.messages[m1].acknowledged == set(range(8))
    at_most_once = b.delivery_order == [m2, m1]
    held_after_ack = b.buffered_bytes == 11 and a.peer_credit_limit == 16
    assert b.consume_message(m2) == b"XYZ"
    assert b.consume_message(m1) == b"abcdefgh"
    assert fixture.transmit(b.make_feedback(), 18) == "accepted"
    released_on_consume = b.buffered_bytes == 0 and a.peer_credit_limit == 27
    continued_id = a.queue_message(b"new") == 2
    reverse_id = b.queue_message(b"back")
    reverse_packet = require_packet(b, 19)
    assert fixture.transmit(reverse_packet, 20) == "accepted"
    full_duplex = a.completed[reverse_id] == b"back"
    second_a, second_b = establish_channel(fixture.left, fixture.right, maximum_message_size=16)
    distinct_tokens = (
        second_a.local_receive_token != a.local_receive_token and second_b.local_receive_token != b.local_receive_token
    )
    fixture.right.close(second_b.local_receive_token)
    third_a, third_b = establish_channel(fixture.left, fixture.right, maximum_message_size=16)
    stale_token_packet = ChannelPacket.create(a.local_eid, a.remote_eid, second_b.local_receive_token, 0, lost.frame)
    stale_token_status = fixture.right.receive(ChannelEnvelope(stale_token_packet), 21)
    safe_tokens = stale_token_status == "unknown_token" and third_b.local_receive_token != second_b.local_receive_token
    scale5 = scale5_probe()
    scale5_criteria = scale5["criteria"]
    assert isinstance(scale5_criteria, dict)
    raw_unchanged = scale5_criteria["locator_only_traffic"] is True
    return {
        "schema": "netsynth.scale6.semantic-probe.v1",
        "topology": fixture.graph.to_dict(),
        "parameters": {
            "seed": None,
            "generator": "hand-built-five-node-chain",
            "maximum_message_size": 16,
            "remote_receive_capacity": 16,
            "pmtu_bytes": [68, 66],
            "header_accounting_bytes": 64,
            "loss": [lost.packet_number],
            "ordering": "second-fragment-before-first; M2-before-M1",
            "congestion": "two-packet-initial-window, one-packet-per-tick, halve-on-loss-or-mark toy",
            "integrity": "CRC32 over endpoint transport model fields; not authentication or wire format",
            "token_entropy": "deterministic-fixture-only",
        },
        "results": {
            "delivery_order": b.delivery_order,
            "lost_packet_number": lost.packet_number,
            "retransmission_packet_numbers": [retransmission.packet_number, remainder.packet_number],
            "fragment_sizes_after_migration": [retransmission.size, remainder.size],
            "stale_attachment": stale_status,
            "binding_version_after_migration": binding_version,
            "corruption": corrupt_status,
            "stale_token": stale_token_status,
            "flow_credit_after_consumption": a.peer_credit_limit,
            "old_path_marks": old_path.congestion_marks,
            "new_path_marks": new_path.congestion_marks,
            "sequential_header_length": new_path.program.sequential_header_length,
            "transit_channel_records": 0,
        },
        "criteria": {
            "channel_survives_binding_locator_program_replacement": fixture.a is a
            and binding_version > fixture.initial.version
            and full_duplex,
            "multiple_channels_same_eid_pair": distinct_tokens and third_a.remote_eid == a.remote_eid,
            "stale_unknown_tokens_fail_closed": safe_tokens,
            "loss_retransmits_needed_data_with_new_packet_number": retransmission.packet_number > lost.packet_number
            and all_acked,
            "duplicate_reordered_fragments_deliver_at_most_once": at_most_once,
            "M2_delivered_while_M1_incomplete": delivered_early,
            "packet_and_message_spaces_continue": continued_id and retransmission.packet_number > third.packet_number,
            "flow_credit_survives_migration_not_ACK": credit_preserved and held_after_ack and released_on_consume,
            "independent_new_path_state": conservative and independent_pmtu,
            "late_old_ACK_cannot_mutate_new_path": late_ack_isolated,
            "congestion_feedback_attributed_to_sent_path": marks_attributed,
            "integrity_before_channel_mutation": corrupt_status == "corrupt" and unchanged_by_corruption,
            "no_stream_lane_subchannel_port": all(
                not any(word in name for word in ("stream", "lane", "subchannel", "port")) for name in vars(a)
            ),
            "raw_locator_only_without_channel_state": raw_unchanged and before == fixture.routing_snapshot(),
        },
    }
