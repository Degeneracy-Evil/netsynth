"""Tiny compiled-forwarding model: fixed packets, reusable owner-local bindings.

Word/record sizes below are an accounting profile, NOT a proposed wire format.
Only the explicitly privileged packet-heavy control expands descendant paths.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, Protocol

from netsynth.graph import Graph
from netsynth.scale4 import AdvertisedPathlet, PathletHandle, PathletRegistry, PhysicalHop

WORD_BYTES = 8
HANDLE_BYTES = 12


@dataclass(frozen=True)
class ResourceContract:
    """Immediate-child advertisement with a conservative writable-context bound."""

    advertisement: AdvertisedPathlet
    context_words: int

    def __post_init__(self) -> None:
        if self.context_words < 0:
            raise ValueError("negative advertised context requirement")


@dataclass(frozen=True)
class BindingRef:
    """Scope-local token; never an EID, Channel or flow identifier."""

    owner: str
    token: int


@dataclass(frozen=True)
class Instruction:
    """One physical hop, child call or return, with an exact-generation guard."""

    guard: PathletHandle
    hop: PhysicalHop | None = None
    next_ref: BindingRef | None = None
    child: BindingRef | None = None
    push: bool = False

    @property
    def size_bytes(self) -> int:
        """Charge opcode, guard, physical action and all stored references."""
        return (
            1
            + HANDLE_BYTES
            + WORD_BYTES * (int(self.hop is not None) + int(self.next_ref is not None) + int(self.child is not None))
        )


class ChildCompiler(Protocol):
    """Parent-visible interface: no registry, realization or graph accessor."""

    def contract(self, handle: PathletHandle) -> ResourceContract: ...

    def install(self, handle: PathletHandle, continuation: BindingRef | None, capacity: int) -> BindingRef: ...


class LocalCompiler:
    """Compile only owner actions and immediate-child public contracts.

    A continuation-specialized entry is reusable at a common STP call site.
    The supplied return reference is opaque; children never inspect its owner.
    """

    def __init__(self, registry: PathletRegistry, children: Mapping[str, ChildCompiler]) -> None:
        self.registry = registry
        self.children = dict(children)
        self.table: dict[BindingRef, Instruction] = {}
        self._variants: dict[tuple[PathletHandle, BindingRef | None, int], tuple[BindingRef, ...]] = {}
        self._requirements: dict[PathletHandle, int] = {}
        self._next_token = 0
        self.update_records = 0

    def _required(self, actions: tuple[PhysicalHop | PathletHandle, ...]) -> int:
        return max(
            (
                1 + self.children[action.owner_scope].contract(action).context_words
                for action in actions
                if isinstance(action, PathletHandle)
            ),
            default=0,
        )

    def _actions(self, handle: PathletHandle) -> tuple[PhysicalHop | PathletHandle, ...]:
        pathlet = self.registry.lookup(handle)
        if pathlet is None:
            raise ValueError("stale pathlet")
        actions: list[PhysicalHop | PathletHandle] = []
        for action in pathlet.realization:
            if not isinstance(action, (PhysicalHop, PathletHandle)):
                raise ValueError("query-local Access is not a reusable binding")
            actions.append(action)
        return tuple(actions)

    def contract(self, handle: PathletHandle) -> ResourceContract:
        """Export no hidden realization; compose immediate-child requirements."""
        pathlet = self.registry.lookup(handle)
        if pathlet is None:
            raise ValueError("stale pathlet")
        if handle not in self._requirements:
            self._requirements[handle] = self._required(self._actions(handle))
        return ResourceContract(pathlet.advertisement, self._requirements[handle])

    def install(self, handle: PathletHandle, continuation: BindingRef | None, capacity: int) -> BindingRef:
        """Use reserved context where possible; spill continuations into bindings."""
        if capacity < 0:
            raise ValueError("negative context capacity")
        self.contract(handle)
        key = handle, continuation, capacity
        if key in self._variants:
            return self._variants[key][0]
        actions = self._actions(handle)
        refs = self._allocate(len(actions) + 1)
        self._variants[key] = refs
        self._write(handle, continuation, capacity, refs, actions)
        return refs[0]

    def _allocate(self, count: int) -> tuple[BindingRef, ...]:
        refs = tuple(BindingRef(self.registry.scope_id, self._next_token + index) for index in range(count))
        self._next_token += count
        return refs

    def _write(
        self,
        handle: PathletHandle,
        continuation: BindingRef | None,
        capacity: int,
        refs: tuple[BindingRef, ...],
        actions: tuple[PhysicalHop | PathletHandle, ...],
    ) -> None:
        for index, action in enumerate(actions):
            resume = refs[index + 1]
            if isinstance(action, PhysicalHop):
                instruction = Instruction(handle, hop=action, next_ref=resume)
            else:
                child = self.children[action.owner_scope]
                push = child.contract(action).context_words < capacity
                entry = child.install(action, None if push else resume, capacity - 1 if push else capacity)
                instruction = Instruction(handle, next_ref=resume, child=entry, push=push)
            self.table[refs[index]] = instruction
            self.update_records += 1
        self.table[refs[-1]] = Instruction(handle, next_ref=continuation)
        self.update_records += 1

    def repair(self, handle: PathletHandle, actions: tuple[PhysicalHop | PathletHandle, ...]) -> None:
        """Preserve entry tokens and hard resource requirement during local repair."""
        bound = self.contract(handle).context_words
        if self._required(actions) > bound:
            raise ValueError("repair exceeds hard resource contract; requires a new generation")
        self.registry.repair(handle, actions)
        for (variant, continuation, capacity), old_refs in tuple(self._variants.items()):
            if variant != handle:
                continue
            # Entry reference remains stable even if the hidden action count changes.
            refs = (old_refs[0], *self._allocate(len(actions)))
            for old_ref in old_refs:
                del self.table[old_ref]
                self.update_records += 1
            self._variants[variant, continuation, capacity] = refs
            self._write(handle, continuation, capacity, refs, actions)

    @property
    def state_bytes(self) -> int:
        """Charge tokens, instructions, hard requirements and compiler variant keys."""
        return (
            sum(WORD_BYTES + item.size_bytes for item in self.table.values())
            + len(self._requirements) * (HANDLE_BYTES + WORD_BYTES)
            + sum(HANDLE_BYTES + 2 * WORD_BYTES + len(refs) * WORD_BYTES for refs in self._variants.values())
            + WORD_BYTES  # Monotonic local token allocator, not a retired-token set.
        )


@dataclass(frozen=True)
class InlineHop:
    """Privileged packet-heavy control includes physical detail and ancestry guards."""

    hop: PhysicalHop
    guards: tuple[PathletHandle, ...]


type CodeAction = PhysicalHop | BindingRef | InlineHop


@dataclass(frozen=True)
class CompiledProgram:
    """Finite immutable code plus pre-reserved context, known before packetization."""

    mode: Literal["packet-heavy", "state-heavy", "hybrid"]
    code: tuple[CodeAction, ...]
    context_words: int

    @property
    def code_bytes(self) -> int:
        """Explicit profile charge; identifiers count even in the comparison control."""
        return sum(
            1 + WORD_BYTES + (len(action.guards) * HANDLE_BYTES if isinstance(action, InlineHop) else 0)
            for action in self.code
        )

    @property
    def context_bytes(self) -> int:
        """Cursor/current token/depth are fixed working words, plus continuation slots."""
        return (3 + self.context_words) * WORD_BYTES


def compile_hybrid(
    actions: tuple[PhysicalHop | PathletHandle, ...], children: Mapping[str, ChildCompiler], capacity: int
) -> CompiledProgram:
    """Ingress knows only owner-visible hops and immediate-child interfaces."""
    if capacity < 0:
        raise ValueError("negative context capacity")
    code: list[CodeAction] = []
    for action in actions:
        if isinstance(action, PhysicalHop):
            code.append(action)
        else:
            code.append(children[action.owner_scope].install(action, None, capacity))
    return CompiledProgram("hybrid", tuple(code), capacity)


def compile_packet_heavy(
    actions: tuple[PhysicalHop | PathletHandle, ...], registries: Mapping[str, PathletRegistry]
) -> CompiledProgram:
    """Explicit descendant-knowledge oracle CONTROL, never the hybrid compiler."""
    code: list[CodeAction] = []

    def expand(items: tuple[PhysicalHop | PathletHandle, ...], guards: tuple[PathletHandle, ...]) -> None:
        for action in items:
            if isinstance(action, PhysicalHop):
                code.append(InlineHop(action, guards))
            else:
                pathlet = registries[action.owner_scope].lookup(action)
                if pathlet is None:
                    raise ValueError("stale pathlet")
                child_actions: list[PhysicalHop | PathletHandle] = []
                for item in pathlet.realization:
                    if not isinstance(item, (PhysicalHop, PathletHandle)):
                        raise ValueError("Access expansion is outside this transit fixture")
                    child_actions.append(item)
                expand(tuple(child_actions), (*guards, action))

    expand(actions, ())
    return CompiledProgram("packet-heavy", tuple(code), 0)


def compile_state_heavy(owner: LocalCompiler, route_handle: PathletHandle) -> CompiledProgram:
    """Comparison only: an installed reusable whole-route macro, no continuation slots."""
    return CompiledProgram("state-heavy", (owner.install(route_handle, None, 0),), 0)


@dataclass(frozen=True)
class PacketBudget:
    """Ingress packetizer charges routing and network/Channel/security envelope."""

    usable_size: int
    envelope_bytes: int

    def payload_capacity(self, program: CompiledProgram) -> int:
        capacity = self.usable_size - self.envelope_bytes - program.code_bytes - program.context_bytes
        if capacity < 0 or self.envelope_bytes < 0:
            raise ValueError("compiled header does not fit usable packet size")
        return capacity


@dataclass(frozen=True)
class Execution:
    """Logical processing costs, not timings or a hardware performance claim."""

    status: str
    path: tuple[int, ...]
    lookups: int
    generation_checks: int
    context_mutations: int
    maximum_context_words: int
    wire_sizes: tuple[int, ...]


def execute(
    graph: Graph,
    owners: Mapping[str, LocalCompiler],
    registries: Mapping[str, PathletRegistry],
    program: CompiledProgram,
    source: int,
    destination: int,
    budget: PacketBudget,
    payload_bytes: int,
    hop_budget: int = 32,
) -> Execution:
    """Dispatch local tokens without expanding packet code or using a hidden stack."""
    if not 0 <= payload_bytes <= budget.payload_capacity(program):
        raise ValueError("payload exceeds ingress capacity")
    wire = budget.envelope_bytes + program.code_bytes + program.context_bytes + payload_bytes
    sizes = [wire]
    slots: list[BindingRef | None] = [None] * program.context_words
    depth = peak = lookups = mutations = checks = cursor = 0
    active: BindingRef | None = None
    path = [source]
    status = "delivered"
    # A separate finite instruction bound also prevents malformed zero-hop cycles.
    for _ in range(1024):
        hop: PhysicalHop | None = None
        instruction: Instruction | None = None
        guards: tuple[PathletHandle, ...] = ()
        if active is None:
            if cursor == len(program.code):
                if depth or path[-1] != destination:
                    status = "contract_violation"
                break
            action = program.code[cursor]
            cursor += 1
            mutations += 1
            if isinstance(action, BindingRef):
                active = action
                mutations += 1
                continue
            if isinstance(action, InlineHop):
                hop, guards = action.hop, action.guards
            else:
                hop = action
        else:
            owner = owners.get(active.owner)
            instruction = None if owner is None else owner.table.get(active)
            lookups += 1
            if instruction is None:
                status = "unknown_binding"
                break
            guards = (instruction.guard,)
            hop = instruction.hop
        checks += len(guards)
        if any(registries[guard.owner_scope].lookup(guard) is None for guard in guards):
            status = "stale_pathlet"
            break
        if active is not None:
            assert instruction is not None
            if instruction.child is not None:
                if instruction.push:
                    if depth == len(slots):
                        status = "context_exhausted"
                        break
                    slots[depth] = instruction.next_ref
                    depth += 1
                    peak = max(peak, depth)
                    mutations += 2
                active = instruction.child
            elif instruction.hop is not None or instruction.next_ref is not None:
                active = instruction.next_ref
            elif depth:
                depth -= 1
                active, slots[depth] = slots[depth], None
                mutations += 2
            else:
                active = None
            mutations += 1
        if hop is not None:
            if len(path) - 1 >= hop_budget:
                status = "hop_budget_exhausted"
                break
            if path[-1] != hop.left or graph.edge(hop.left, hop.right) is None:
                status = "invalid_physical_hop"
                break
            path.append(hop.right)
        actual_size = budget.envelope_bytes + program.code_bytes + (3 + len(slots)) * WORD_BYTES + payload_bytes
        if actual_size > wire:
            raise AssertionError("forwarding grew the ingress packet")
        sizes.append(actual_size)
    else:
        status = "instruction_budget_exhausted"
    return Execution(status, tuple(path), lookups, checks, mutations, peak, tuple(sizes))
