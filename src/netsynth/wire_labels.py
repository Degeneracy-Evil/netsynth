"""Independent label-swap control compiler and per-node LFIB interpreter.

No NetRow, NetPacket or NetNode reuse. STPs become continuation-specialized
local policies. No label reuse (20-bit exhaustion rejects) substitutes for
carrying a hard generation on wire in this bounded-lifetime comparison.
"""

from __future__ import annotations

import struct
from dataclasses import asdict, dataclass, field

from netsynth.forwarding_program_probe import Fixture, fixture
from netsynth.scale4 import PathletHandle, PathletRegistry, PhysicalHop
from netsynth.wire_forwarding import Operations
from netsynth.wire_packet import Attachment, LabelPacket


@dataclass(frozen=True)
class LabelAddress:
    """Control-plane install response; node ID is NOT in the packet label."""

    node: int
    label: int


@dataclass(frozen=True)
class LabelRow:
    scope: int
    slot: int
    generation: int
    opcode: int  # 0: local swap; 1: physical output+swap; 2: endpoint delivery
    port: int = 0
    next_label: int = 0

    def encode(self, label: int) -> bytes:
        return struct.pack(
            "!IH I I B H I", label, self.scope, self.slot, self.generation, self.opcode, self.port, self.next_label
        )


@dataclass
class LabelNode:
    identifier: int
    table: dict[int, LabelRow] = field(default_factory=dict)
    generations: dict[tuple[int, int], int] = field(default_factory=dict)
    links: dict[int, LabelNode] = field(default_factory=dict)
    operations: Operations = field(default_factory=Operations)
    attachment: Attachment | None = None
    next_label: int = 16

    def allocate(self, row: LabelRow) -> int:
        if self.next_label >= 2**20:
            raise ValueError("label namespace exhausted; no unsafe reuse")
        label = self.next_label
        self.next_label += 1
        self.table[label] = row
        if self.generations.get((row.scope, row.slot)) != row.generation:
            self.generations[row.scope, row.slot] = row.generation
        return label

    def state_image(self) -> bytes:
        return (
            b"".join(row.encode(label) for label, row in sorted(self.table.items()))
            + b"".join(struct.pack("!HII", scope, slot, gen) for (scope, slot), gen in sorted(self.generations.items()))
            + b"".join(struct.pack("!HH", port, peer.identifier) for port, peer in sorted(self.links.items()))
            + struct.pack("!I", self.next_label)
        )

    def step(self, data: bytes) -> tuple[str, bytes, int]:
        self.operations.parses += 1
        try:
            packet = LabelPacket.decode(data)
        except ValueError, struct.error, IndexError:
            return "malformed", data, 0
        for _ in range(128):
            self.operations.table_lookups += 1
            row = self.table.get(packet.label)
            if row is None:
                return "unknown_label", data, 0
            self.operations.guard_lookups += 1
            if self.generations.get((row.scope, row.slot)) != row.generation:
                return "stale_generation", data, 0
            self.operations.local_actions += 1
            if row.opcode == 2:
                status = "wrong_attachment" if self.attachment is None else self.attachment.deliver(packet)
                return status, self._serialize(packet, data), 0
            if row.opcode == 0:
                packet.label = row.next_label
                continue
            if row.opcode != 1:
                return "invalid_action", data, 0
            if not packet.hops:
                return "hop_budget_exhausted", data, 0
            if row.port not in self.links:
                return "link_down", data, 0
            packet.hops -= 1
            packet.label = row.next_label
            encoded = self._serialize(packet, data)
            self.operations.physical_hops += 1
            return "forward", encoded, row.port
        return "work_budget_exhausted", data, 0

    def _serialize(self, packet: LabelPacket, original: bytes) -> bytes:
        encoded = packet.encode()
        if len(encoded) != len(original):
            raise AssertionError("label packet grew in transit")
        self.operations.changed_header_bytes += sum(
            a != b for a, b in zip(encoded[: len(packet.header())], original, strict=False)
        )
        self.operations.serializations += 1
        return encoded


class LocalPolicy:
    """Own realization plus immediate-child install/endpoint contracts only."""

    def __init__(
        self, registry: PathletRegistry, scope: int, nodes: dict[int, LabelNode], children: dict[str, LocalPolicy]
    ) -> None:
        self.registry, self.scope, self.nodes, self.children = registry, scope, nodes, children
        self._variants: dict[tuple[PathletHandle, LabelAddress | None], tuple[LabelAddress, list[LabelAddress]]] = {}

    def _new(self, node: int, handle: PathletHandle, opcode: int, port: int = 0, next_label: int = 0) -> LabelAddress:
        if not 0 <= handle.generation < 0xFFFFFFFF:
            raise ValueError("generation exhaustion")
        label = self.nodes[node].allocate(
            LabelRow(self.scope, handle.slot, handle.generation, opcode, port, next_label)
        )
        return LabelAddress(node, label)

    def install(self, handle: PathletHandle, continuation: LabelAddress | None) -> LabelAddress:
        key = handle, continuation
        if key in self._variants:
            return self._variants[key][0]
        pathlet = self.registry.lookup(handle)
        if pathlet is None:
            raise ValueError("stale policy")
        # Stable public label, hidden internal action chain.
        entry = self._new(pathlet.advertisement.ingress, handle, 0)
        internals = self._write(handle, continuation, entry)
        self._variants[key] = entry, internals
        return entry

    def _write(
        self, handle: PathletHandle, continuation: LabelAddress | None, entry: LabelAddress
    ) -> list[LabelAddress]:
        pathlet = self.registry.lookup(handle)
        assert pathlet is not None
        internals: list[LabelAddress] = []
        if continuation is None:
            continuation = self._new(pathlet.advertisement.egress, handle, 2)
            internals.append(continuation)
        elif continuation.node != pathlet.advertisement.egress:
            raise ValueError("return contract boundary mismatch")
        current = continuation
        for action in reversed(pathlet.realization):
            if isinstance(action, PhysicalHop):
                if current.node != action.right:
                    raise ValueError("discontinuous local label policy")
                current = self._new(action.left, handle, 1, action.right + 1, current.label)
                internals.append(current)
            elif isinstance(action, PathletHandle):
                current = self.children[action.owner_scope].install(action, current)
            else:
                raise ValueError("query Access is outside this transit fixture")
        if current.node != entry.node:
            raise ValueError("entry boundary mismatch")
        self.nodes[entry.node].table[entry.label] = LabelRow(
            self.scope, handle.slot, handle.generation, 0, 0, current.label
        )
        return internals

    def repair(self, handle: PathletHandle, actions: tuple[PhysicalHop, ...]) -> None:
        self.registry.repair(handle, actions)
        for (variant, continuation), (entry, old) in tuple(self._variants.items()):
            if variant == handle:
                for address in old:
                    del self.nodes[address.node].table[address.label]
                internals = self._write(handle, continuation, entry)
                self._variants[variant, continuation] = entry, internals

    def withdraw(self, handle: PathletHandle) -> None:
        self.registry.retire(handle)
        for node in self.nodes.values():
            if (self.scope, handle.slot) in node.generations:
                node.generations[self.scope, handle.slot] = 0xFFFFFFFF


@dataclass
class LabelControl:
    model: Fixture
    nodes: dict[int, LabelNode]
    policies: dict[str, LocalPolicy]
    entry: LabelAddress

    def repair(self) -> None:
        self.policies["leaf"].repair(
            self.model.handles["leaf"], (PhysicalHop(1, 4), PhysicalHop(4, 8), PhysicalHop(8, 3))
        )


def build_labels() -> LabelControl:
    model = fixture()  # Independently compile ARP, never read the NetSynth wire tables.
    nodes = {node: LabelNode(node) for node in model.graph.nodes}
    for edge in model.graph.edges:
        nodes[edge.left].links[edge.right + 1] = nodes[edge.right]
        nodes[edge.right].links[edge.left + 1] = nodes[edge.left]
    policies: dict[str, LocalPolicy] = {}
    children = {"leaf": None, "inner": "leaf", "middle": "inner", "root": "middle"}
    for scope, name in enumerate(("leaf", "inner", "middle", "root"), start=1):
        child = children[name]
        policies[name] = LocalPolicy(
            model.registries[name], scope, nodes, {} if child is None else {child: policies[child]}
        )
    entry = policies["root"].install(model.handles["root"], None)
    return LabelControl(model, nodes, policies, entry)


def run_labels(source: LabelNode, data: bytes) -> dict[str, object]:
    node = source
    path, sizes = [node.identifier], [len(data)]
    for _ in range(256):
        status, data, port = node.step(data)
        sizes.append(len(data))
        if status != "forward":
            return {"status": status, "path": tuple(path), "wire_sizes": tuple(sizes), "final_hex": data.hex()}
        node = node.links[port]
        path.append(node.identifier)
    return {"status": "hop_budget_exhausted", "path": tuple(path), "wire_sizes": tuple(sizes)}


def label_metrics(nodes: dict[int, LabelNode]) -> dict[str, object]:
    return {
        str(n): {
            "table_records": len(node.table),
            "table_image_bytes": sum(len(row.encode(label)) for label, row in node.table.items()),
            "generation_image_bytes": len(node.generations) * 10,
            "port_image_bytes": len(node.links) * 4,
            "allocator_image_bytes": 4,
            "state_image_bytes": len(node.state_image()),
            "operations": asdict(node.operations),
        }
        for n, node in sorted(nodes.items())
    }
