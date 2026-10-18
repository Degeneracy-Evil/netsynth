"""Lower existing Scope-local bindings to per-physical-node wire forwarding.

Control-plane conversion consumes only owner instructions and immediate-child
entry advertisements. NetNode.step has NO owner map, registry, or graph.
"""

from __future__ import annotations

import struct
from dataclasses import asdict, dataclass, field

from netsynth.forwarding_program import (
    BindingRef,
    CompiledProgram,
    LocalCompiler,
    ResourceContract,
    compile_hybrid,
    compile_state_heavy,
)
from netsynth.forwarding_program_probe import Fixture, fixture
from netsynth.scale4 import PathletHandle, PhysicalHop
from netsynth.wire_packet import EMPTY, Attachment, NetPacket, WireKey

SCOPES = {"root": 1, "middle": 2, "inner": 3, "leaf": 4}


@dataclass
class Operations:
    parses: int = 0
    table_lookups: int = 0
    guard_lookups: int = 0
    code_reads: int = 0
    local_actions: int = 0
    physical_hops: int = 0
    changed_header_bytes: int = 0
    serializations: int = 0


@dataclass(frozen=True)
class NetRow:
    slot: int
    port: int = 0
    next_key: WireKey = EMPTY
    child: WireKey = EMPTY
    push: bool = False

    def encode(self, key: WireKey) -> bytes:
        return (
            key.encode()
            + struct.pack("!IH?", self.slot, self.port, self.push)
            + self.next_key.encode()
            + self.child.encode()
        )


@dataclass
class NetNode:
    identifier: int
    table: dict[WireKey, NetRow] = field(default_factory=dict)
    generations: dict[tuple[int, int], int] = field(default_factory=dict)
    links: dict[int, NetNode] = field(default_factory=dict)
    operations: Operations = field(default_factory=Operations)
    attachment: Attachment | None = None

    def state_image(self) -> bytes:
        """Exact canonical record image, NOT CPython heap/ASIC memory usage."""
        return (
            b"".join(row.encode(key) for key, row in sorted(self.table.items(), key=lambda item: item[0].encode()))
            + b"".join(struct.pack("!HII", scope, slot, gen) for (scope, slot), gen in sorted(self.generations.items()))
            + b"".join(struct.pack("!HH", port, peer.identifier) for port, peer in sorted(self.links.items()))
        )

    def step(self, data: bytes) -> tuple[str, bytes, int]:
        self.operations.parses += 1
        try:
            packet = NetPacket.decode(data)
        except ValueError, struct.error, IndexError:
            return "malformed", data, 0
        for _ in range(128):
            if packet.current == EMPTY:
                if packet.cursor == len(packet.code):
                    if packet.depth:
                        return "bad_context", data, 0
                    status = "wrong_attachment" if self.attachment is None else self.attachment.deliver(packet)
                    return status, self._serialize(packet, data), 0
                packet.current = packet.code[packet.cursor]
                packet.cursor += 1
                self.operations.code_reads += 1
            self.operations.table_lookups += 1
            row = self.table.get(packet.current)
            if row is None:
                return "unknown_token", data, 0
            self.operations.guard_lookups += 1
            if self.generations.get((packet.current.scope, row.slot)) != packet.current.generation:
                return "stale_generation", data, 0
            self.operations.local_actions += 1
            if row.child != EMPTY:
                if row.push:
                    if packet.depth == len(packet.slots):
                        return "context_exhausted", data, 0
                    packet.slots[packet.depth] = row.next_key
                    packet.depth += 1
                packet.current = row.child
            elif row.port:
                if not packet.hops:
                    return "hop_budget_exhausted", data, 0
                if row.port not in self.links:
                    return "link_down", data, 0
                packet.hops -= 1
                packet.current = row.next_key
                encoded = self._serialize(packet, data)
                self.operations.physical_hops += 1
                return "forward", encoded, row.port
            elif row.next_key != EMPTY:
                packet.current = row.next_key
            elif packet.depth:
                packet.depth -= 1
                packet.current = packet.slots[packet.depth]
                packet.slots[packet.depth] = EMPTY
            else:
                packet.current = EMPTY
        return "work_budget_exhausted", data, 0

    def _serialize(self, packet: NetPacket, original: bytes) -> bytes:
        encoded = packet.encode()
        if len(encoded) != len(original):
            raise AssertionError("packet grew in transit")
        self.operations.changed_header_bytes += sum(
            a != b for a, b in zip(encoded[: len(packet.header())], original, strict=False)
        )
        self.operations.serializations += 1
        return encoded


@dataclass(frozen=True)
class EntryAdvertisement:
    handle: PathletHandle
    ingress: int
    egress: int


class InstallInterface:
    """Only control-plane install RPC and public resource/entry contracts."""

    def __init__(self, owner: LocalCompiler) -> None:
        self._owner = owner
        self.entries: dict[BindingRef, EntryAdvertisement] = {}
        self.return_refs: set[BindingRef] = set()
        self.return_keys: dict[BindingRef, WireKey] = {}

    def contract(self, handle: PathletHandle) -> ResourceContract:
        return self._owner.contract(handle)

    def install(self, handle: PathletHandle, continuation: BindingRef | None, capacity: int) -> BindingRef:
        contract = self.contract(handle).advertisement
        entry = self._owner.install(handle, continuation, capacity)
        self.entries[entry] = EntryAdvertisement(handle, contract.ingress, contract.egress)
        if continuation is not None:
            self.return_refs.add(continuation)
        return entry


def key_for(ref: BindingRef, owner: LocalCompiler) -> WireKey:
    if ref.token >= 0xFFFF0000:
        raise ValueError("compiler token space exhausted; upper range reserved for crossing actions")
    instruction = owner.table[ref]
    key = WireKey(SCOPES[ref.owner], ref.token, instruction.guard.generation)
    key.encode()  # Width exhaustion rejects, never wraps.
    return key


def lower_owner(
    owner: LocalCompiler, exports: dict[BindingRef, EntryAdvertisement], returns: dict[BindingRef, WireKey]
) -> dict[int, dict[WireKey, NetRow]]:
    """No descendant instructions: own table and immediate-child advertisements only."""
    rows: dict[int, dict[WireKey, NetRow]] = {}

    def reference(ref: BindingRef | None) -> WireKey:
        if ref is None:
            return EMPTY
        if ref.owner == owner.registry.scope_id:
            return key_for(ref, owner)
        if ref in returns:
            return returns[ref]
        advertised = exports[ref]
        return WireKey(SCOPES[ref.owner], ref.token, advertised.handle.generation)

    for ref, instruction in owner.table.items():
        hard = owner.registry.lookup(instruction.guard)
        if hard is None:
            continue
        if instruction.hop is not None:
            node = instruction.hop.left
            # Port identifiers are fixture-local link-interface numbers, not global owner lookups.
            port = instruction.hop.right + 1
        elif instruction.child is not None:
            node = exports[instruction.child].ingress
            port = 0
        else:
            node = hard.advertisement.egress
            port = 0
        rows.setdefault(node, {})[key_for(ref, owner)] = NetRow(
            instruction.guard.slot,
            port,
            reference(instruction.next_ref),
            reference(instruction.child),
            instruction.push,
        )
    return rows


@dataclass
class NetControl:
    """Experiment harness retains control state, never reachable from NetNode."""

    model: Fixture
    services: dict[str, InstallInterface]
    nodes: dict[int, NetNode]
    program: CompiledProgram
    code: tuple[WireKey, ...]

    def install_rows(self, selected: tuple[str, ...] | None = None) -> None:
        # Caller exports opaque return keys to immediate callees; no child opens a parent table.
        if selected is None:
            for parent in self.model.owners.values():
                for child in parent.children:
                    interface = self.services[child]
                    interface.return_keys = {
                        ref: key_for(ref, parent)
                        for ref in interface.return_refs
                        if ref.owner == parent.registry.scope_id
                    }
        for name in tuple(self.model.owners) if selected is None else selected:
            owner = self.model.owners[name]
            exports = {ref: ad for child in owner.children for ref, ad in self.services[child].entries.items()}
            desired = lower_owner(owner, exports, self.services[name].return_keys)
            if name == "root":
                for index, action in enumerate(self.program.code):
                    if isinstance(action, PhysicalHop):
                        key = WireKey(SCOPES["root"], 0xFFFF0000 + index, 0)
                        desired.setdefault(action.left, {})[key] = NetRow(1 + index, action.right + 1)
            for node_id, node in self.nodes.items():
                rows = desired.get(node_id, {})
                for old in tuple(node.table):
                    if old.scope == SCOPES[name] and old not in rows:
                        del node.table[old]
                for key, row in rows.items():
                    if node.table.get(key) != row:
                        node.table[key] = row
                for key, row in rows.items():
                    if node.generations.get((key.scope, row.slot)) != key.generation:
                        node.generations[key.scope, row.slot] = key.generation

    def repair(self) -> None:
        self.model.owners["leaf"].repair(
            self.model.handles["leaf"], (PhysicalHop(1, 4), PhysicalHop(4, 8), PhysicalHop(8, 3))
        )
        self.install_rows(("leaf",))

    def withdraw(self, handle: PathletHandle) -> None:
        self.model.registries[handle.owner_scope].retire(handle)
        # A control message only to nodes that already hold this owner's guard.
        for node in self.nodes.values():
            if (SCOPES[handle.owner_scope], handle.slot) in node.generations:
                node.generations[SCOPES[handle.owner_scope], handle.slot] = 0xFFFFFFFF


def build_net(mode: str = "warm", capacity: int = 2) -> NetControl:
    model = fixture()
    services = {name: InstallInterface(owner) for name, owner in model.owners.items()}
    for owner in model.owners.values():
        owner.children = {child: services[child] for child in owner.children}
    if mode == "warm":
        program = compile_state_heavy(model.owners["root"], model.handles["root"])
    elif mode == "explicit":
        program = compile_hybrid(model.actions, {"middle": services["middle"]}, capacity)
    else:
        raise ValueError("unknown encoding")
    nodes = {node: NetNode(node) for node in model.graph.nodes}
    for edge in model.graph.edges:
        nodes[edge.left].links[edge.right + 1] = nodes[edge.right]
        nodes[edge.right].links[edge.left + 1] = nodes[edge.left]
    control = NetControl(model, services, nodes, program, ())
    control.install_rows()
    code: list[WireKey] = []
    for index, action in enumerate(program.code):
        if isinstance(action, BindingRef):
            code.append(key_for(action, model.owners[action.owner]))
        elif isinstance(action, PhysicalHop):
            key = WireKey(SCOPES["root"], 0xFFFF0000 + index, 0)
            code.append(key)
        else:
            raise ValueError("descendant-expanded control is not a wire architecture")
    control.code = tuple(code)
    return control


def run_net(source: NetNode, data: bytes) -> dict[str, object]:
    """Only follow physical neighbor ports; no world/owner/registry mapping."""
    node = source
    path, sizes = [source.identifier], [len(data)]
    for _ in range(256):
        status, data, port = node.step(data)
        sizes.append(len(data))
        if status != "forward":
            return {"status": status, "path": tuple(path), "wire_sizes": tuple(sizes), "final_hex": data.hex()}
        node = node.links[port]
        path.append(node.identifier)
    return {"status": "hop_budget_exhausted", "path": tuple(path), "wire_sizes": tuple(sizes)}


def net_metrics(nodes: dict[int, NetNode]) -> dict[str, object]:
    return {
        str(n): {
            "table_records": len(node.table),
            "table_image_bytes": sum(len(row.encode(key)) for key, row in node.table.items()),
            "generation_image_bytes": len(node.generations) * 10,
            "port_image_bytes": len(node.links) * 4,
            "allocator_image_bytes": 0,
            "state_image_bytes": len(node.state_image()),
            "operations": asdict(node.operations),
        }
        for n, node in sorted(nodes.items())
    }
