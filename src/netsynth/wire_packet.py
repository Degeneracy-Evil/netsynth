"""A deliberately small experimental encoding, not a NetSynth wire standard.

Big-endian fields, explicit lengths, no Python objects on links. The independent
label codec uses a single RFC-3032-shaped shim, not the NetSynth interpreter.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from netsynth.forwarding import Locator

NS_PREFIX = struct.Struct("!BBBBHHBBBB")
KEY = struct.Struct("!HII")
TRANSPORT = struct.Struct("!IIII")
TAG_BYTES = 16


@dataclass(frozen=True)
class WireKey:
    """Scope namespace (16), local token (32), exact STP generation (32)."""

    scope: int = 0
    token: int = 0
    generation: int = 0

    def encode(self) -> bytes:
        if self.scope == 0 and (self.token or self.generation):
            raise ValueError("namespace zero reserved for empty key")
        if self.generation == 0xFFFFFFFF:
            raise ValueError("generation exhaustion; inactive sentinel is reserved")
        return KEY.pack(self.scope, self.token, self.generation)

    @classmethod
    def decode(cls, data: bytes) -> WireKey:
        scope, token, generation = KEY.unpack(data)
        key = cls(scope, token, generation)
        key.encode()
        return key


EMPTY = WireKey()


def locator_bytes(locator: Locator) -> bytes:
    return (
        bytes([len(locator.components)])
        + b"".join(struct.pack("!H", v) for v in locator.components)
        + struct.pack("!I", locator.selector)
    )


def read_locator(data: bytes, offset: int) -> tuple[Locator, int]:
    count = data[offset]
    end = offset + 1 + count * 2
    components = tuple(struct.unpack("!H", data[i : i + 2])[0] for i in range(offset + 1, end, 2))
    selector = struct.unpack("!I", data[end : end + 4])[0]
    return Locator(components, selector), end + 4


@dataclass
class NetPacket:
    """Reserved slots never change length, even on a child invocation."""

    locator: Locator
    code: tuple[WireKey, ...]
    slots: list[WireKey]
    transport: tuple[int, int, int, int]
    sealed: bytes
    hops: int = 32
    mark: int = 0
    cursor: int = 0
    depth: int = 0
    current: WireKey = EMPTY

    def header(self) -> bytes:
        rest = (
            self.current.encode()
            + locator_bytes(self.locator)
            + b"".join(k.encode() for k in (*self.code, *self.slots))
            + TRANSPORT.pack(*self.transport)
        )
        length = NS_PREFIX.size + len(rest)
        return (
            NS_PREFIX.pack(
                1,
                0,
                self.hops,
                self.mark,
                length,
                length + len(self.sealed),
                len(self.code),
                self.cursor,
                len(self.slots),
                self.depth,
            )
            + rest
        )

    def encode(self) -> bytes:
        if self.cursor > len(self.code) or self.depth > len(self.slots):
            raise ValueError("cursor/context bounds")
        if not 0 <= self.mark < 8:
            raise ValueError("congestion mark outside shared 3-bit profile")
        return self.header() + self.sealed

    def aad(self) -> bytes:
        # Immutable routing fields are covered; transit cursor/token/context/Hop Budget/mark are not.
        return (
            bytes([1, len(self.code), len(self.slots)])
            + locator_bytes(self.locator)
            + b"".join(k.encode() for k in self.code)
            + TRANSPORT.pack(*self.transport)
        )

    @classmethod
    def decode(cls, data: bytes) -> NetPacket:
        version, flags, hops, mark, header, total, count, cursor, capacity, depth = NS_PREFIX.unpack(
            data[: NS_PREFIX.size]
        )
        if version != 1 or flags or total != len(data) or cursor > count or depth > capacity or mark >= 8:
            raise ValueError("invalid NetSynth framing")
        current = WireKey.decode(data[12:22])
        locator, offset = read_locator(data, 22)
        keys = tuple(WireKey.decode(data[i : i + 10]) for i in range(offset, offset + (count + capacity) * 10, 10))
        offset += (count + capacity) * 10
        transport = TRANSPORT.unpack(data[offset : offset + TRANSPORT.size])
        offset += TRANSPORT.size
        if header != offset or total - header < TAG_BYTES or any(k == EMPTY for k in keys[:count]):
            raise ValueError("invalid NetSynth lengths/code")
        return cls(
            locator, keys[:count], list(keys[count:]), transport, data[offset:], hops, mark, cursor, depth, current
        )


@dataclass
class LabelPacket:
    """Independent one-label format: label20 / TC3 / bottom1 / TTL8."""

    locator: Locator
    label: int
    transport: tuple[int, int, int, int]
    sealed: bytes
    hops: int = 32
    mark: int = 0

    def header(self) -> bytes:
        if not 16 <= self.label < 2**20 or not 0 <= self.hops < 256 or not 0 <= self.mark < 8:
            raise ValueError("label/TTL/TC out of range")
        shim = (self.label << 12) | (self.mark << 9) | 256 | self.hops
        rest = locator_bytes(self.locator) + struct.pack("!I", shim) + TRANSPORT.pack(*self.transport)
        length = 6 + len(rest)
        return struct.pack("!BBHH", 2, 0, length, length + len(self.sealed)) + rest

    def encode(self) -> bytes:
        return self.header() + self.sealed

    def aad(self) -> bytes:
        # Mutable label/TTL/TC are not endpoint integrity fields.
        return b"\x02" + locator_bytes(self.locator) + TRANSPORT.pack(*self.transport)

    @classmethod
    def decode(cls, data: bytes) -> LabelPacket:
        version, flags, header, total = struct.unpack("!BBHH", data[:6])
        locator, offset = read_locator(data, 6)
        shim = struct.unpack("!I", data[offset : offset + 4])[0]
        offset += 4
        transport = TRANSPORT.unpack(data[offset : offset + 16])
        offset += 16
        if version != 2 or flags or total != len(data) or header != offset or total - header < 16 or not shim & 256:
            raise ValueError("invalid label framing")
        packet = cls(locator, shim >> 12, transport, data[offset:], shim & 255, (shim >> 9) & 7)
        packet.header()  # Validate the usable-label range too.
        return packet


type Packet = NetPacket | LabelPacket


def seal(packet: Packet, plaintext: bytes, key: bytes, maximum: int = 512) -> bytes:
    """Fixture-only established traffic key; no handshake or new crypto protocol."""
    packet.sealed = bytes(len(plaintext) + TAG_BYTES)
    if len(packet.encode()) > maximum:
        raise ValueError("packet exceeds ingress size")
    packet.sealed = AESGCM(key).encrypt(bytes(8) + struct.pack("!I", packet.transport[1]), plaintext, packet.aad())
    return packet.encode()


@dataclass
class Attachment:
    """Endpoint-local integrity/demultiplexing witness, not a transport stack."""

    locator: Locator
    key: bytes
    receive_token: int = 7
    received: list[bytes] = field(default_factory=list)
    seen: set[int] = field(default_factory=set)

    def deliver(self, packet: Packet) -> str:
        if packet.locator != self.locator or packet.transport[0] != self.receive_token:
            return "wrong_attachment"
        if packet.transport[1] in self.seen:
            return "duplicate_packet"
        try:
            plain = AESGCM(self.key).decrypt(
                bytes(8) + struct.pack("!I", packet.transport[1]), packet.sealed, packet.aad()
            )
        except InvalidTag:
            return "invalid_integrity"
        self.seen.add(packet.transport[1])
        self.received.append(plain)
        return "delivered"
