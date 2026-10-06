"""One multilayer fixture with repeated child calls and a longer hidden repair."""

from dataclasses import asdict, dataclass
from types import MappingProxyType

from netsynth.decomposition import Scope, ScopeTree
from netsynth.forwarding import Locator
from netsynth.forwarding_program import (
    CompiledProgram,
    LocalCompiler,
    PacketBudget,
    compile_hybrid,
    compile_packet_heavy,
    compile_state_heavy,
    execute,
)
from netsynth.graph import Edge, Graph
from netsynth.scale4 import (
    AdvertisedPathlet,
    PathletHandle,
    PathletRegistry,
    PhysicalHop,
    RouteProgram,
    RouteQueryContext,
    ScopedTransitPathlet,
    execute_route_program,
)


@dataclass
class Fixture:
    """Experiment owner holds global infrastructure; compilers never receive it."""

    graph: Graph
    registries: dict[str, PathletRegistry]
    owners: dict[str, LocalCompiler]
    actions: tuple[PhysicalHop | PathletHandle, ...]
    handles: dict[str, PathletHandle]


def fixture() -> Fixture:
    """Laminar root/middle/inner/leaf with a legal leave/re-entry of the leaf."""
    graph = Graph(
        set(range(10)),
        [
            Edge(a, b)
            for a, b in ((0, 1), (1, 2), (2, 3), (1, 4), (4, 8), (8, 3), (3, 5), (1, 5), (3, 6), (6, 7), (7, 9))
        ],
    )
    leaf = Scope("leaf", frozenset({1, 2, 3, 4, 8}))
    inner = Scope("inner", leaf.members | {5, 6}, (leaf, Scope("i5", frozenset({5})), Scope("i6", frozenset({6}))))
    middle = Scope("middle", inner.members | {7}, (inner, Scope("m7", frozenset({7}))))
    ScopeTree(Scope("root", graph.nodes, (middle, Scope("r0", frozenset({0})), Scope("r9", frozenset({9}))))).validate(
        graph
    )
    handles = {owner: PathletHandle(owner, 0, 0) for owner in ("leaf", "inner", "middle", "root")}
    registries: dict[str, PathletRegistry] = {}
    owners: dict[str, LocalCompiler] = {}

    def add(
        owner: str,
        start: int,
        end: int,
        actions: tuple[PhysicalHop | PathletHandle, ...],
        visible: frozenset[PhysicalHop],
        child: str | None,
    ) -> None:
        btgs = (
            ()
            if child is None
            else (
                registries[child].export(
                    {
                        "leaf": frozenset({1, 3}),
                        "inner": frozenset({1, 6}),
                        "middle": frozenset({1, 7}),
                    }[child]
                ),
            )
        )
        registry = PathletRegistry(owner, visible, btgs)
        registry.publish(ScopedTransitPathlet(AdvertisedPathlet(handles[owner], start, end, 1.0), actions))
        registries[owner] = registry
        owners[owner] = LocalCompiler(registry, {} if child is None else {child: owners[child]})

    leaf_hops = (PhysicalHop(1, 2), PhysicalHop(2, 3))
    add("leaf", 1, 3, leaf_hops, frozenset((*leaf_hops, PhysicalHop(1, 4), PhysicalHop(4, 8), PhysicalHop(8, 3))), None)
    inner_actions = (handles["leaf"], PhysicalHop(3, 5), PhysicalHop(5, 1), handles["leaf"], PhysicalHop(3, 6))
    add("inner", 1, 6, inner_actions, frozenset({PhysicalHop(3, 5), PhysicalHop(5, 1), PhysicalHop(3, 6)}), "leaf")
    add("middle", 1, 7, (handles["inner"], PhysicalHop(6, 7)), frozenset({PhysicalHop(6, 7)}), "inner")
    actions = (PhysicalHop(0, 1), handles["middle"], PhysicalHop(7, 9))
    add("root", 0, 9, actions, frozenset({PhysicalHop(0, 1), PhysicalHop(7, 9)}), "middle")
    return Fixture(graph, registries, owners, actions, handles)


def encoding(model: Fixture, mode: str, capacity: int = 2) -> CompiledProgram:
    """Compile the identical abstract action sequence for each comparison."""
    if mode == "packet-heavy":
        return compile_packet_heavy(model.actions, model.registries)
    if mode == "state-heavy":
        return compile_state_heavy(model.owners["root"], model.handles["root"])
    if mode != "hybrid":
        raise ValueError("unknown encoding")
    return compile_hybrid(model.actions, {"middle": model.owners["middle"]}, capacity)


def run_probe() -> dict[str, object]:
    """Report sizes, processing, persistent state and hidden-repair update locality."""
    rows: dict[str, object] = {}
    for mode, capacity in (("packet-heavy", 0), ("state-heavy", 0), ("hybrid", 2), ("hybrid", 0)):
        model = fixture()  # Isolate state costs; never accumulate modes in one table.
        program = encoding(model, mode, capacity)
        budget = PacketBudget(512, 64)
        payload = budget.payload_capacity(program)
        result = execute(model.graph, model.owners, model.registries, program, 0, 9, budget, payload)
        reference = execute_route_program(
            model.graph,
            MappingProxyType(model.registries),
            MappingProxyType({}),
            RouteProgram(Locator((), 9), model.actions),
            RouteQueryContext("probe", 0),
            32,
        )
        if result.status != "delivered" or result.path != reference.path:
            raise AssertionError("encodings disagree with frozen Scale-4 physical execution")
        state_before = sum(owner.state_bytes for owner in model.owners.values())
        entries_before = sum(len(owner.table) for owner in model.owners.values())
        stp_records_before = sum(registry.persistent_records for registry in model.registries.values())
        updates_before = {name: owner.update_records for name, owner in model.owners.items()}
        model.owners["leaf"].repair(model.handles["leaf"], (PhysicalHop(1, 4), PhysicalHop(4, 8), PhysicalHop(8, 3)))
        repaired_program = encoding(model, mode, capacity) if mode == "packet-heavy" else program
        repaired_payload = min(payload, budget.payload_capacity(repaired_program))
        repaired = execute(
            model.graph, model.owners, model.registries, repaired_program, 0, 9, budget, repaired_payload
        )
        repaired_reference = execute_route_program(
            model.graph,
            MappingProxyType(model.registries),
            MappingProxyType({}),
            RouteProgram(Locator((), 9), model.actions),
            RouteQueryContext("probe", 0),
            32,
        )
        if repaired.status != "delivered" or repaired.path != repaired_reference.path:
            raise AssertionError("repair changed the abstract route semantics")
        model.registries["leaf"].retire(model.handles["leaf"])
        stale = execute(model.graph, model.owners, model.registries, repaired_program, 0, 9, budget, repaired_payload)
        rows[f"{mode}-context-{capacity}"] = {
            "packet_code_bytes": program.code_bytes,
            "packet_code_bits": program.code_bytes * 8,
            "reserved_context_bytes": program.context_bytes,
            "network_channel_security_bytes": budget.envelope_bytes,
            "payload_capacity": payload,
            "header_bytes": program.code_bytes + program.context_bytes + budget.envelope_bytes,
            "binding_state_bytes": state_before,
            "binding_entries": entries_before,
            "binding_entries_after_repair": sum(len(owner.table) for owner in model.owners.values()),
            "binding_state_bytes_after_repair": sum(owner.state_bytes for owner in model.owners.values()),
            "base_stp_state_records": stp_records_before,
            "base_stp_state_records_after_repair": sum(
                registry.persistent_records for registry in model.registries.values()
            ),
            "before": asdict(result),
            "repair": asdict(repaired),
            "outer_code_unchanged": program.code == repaired_program.code,
            "packet_code_update_bytes": 0 if program == repaired_program else repaired_program.code_bytes,
            "stp_realization_update_records": 4,
            "binding_update_records": {
                name: owner.update_records - updates_before[name] for name, owner in model.owners.items()
            },
            "stale_status": stale.status,
        }
    return {
        "schema": "netsynth.forwarding-program.semantic.v1",
        "fixture": {
            "generator": "hand-built",
            "seed": None,
            "nodes": 10,
            "scope_depth": 4,
            "adversarial": "repeated-child-call-and-longer-hidden-repair",
            "sampled": False,
        },
        "profile": {"word_bytes": 8, "handle_bytes": 12, "usable_packet_size": 512, "envelope_bytes": 64},
        "packet_heavy_knowledge": "privileged descendant-expansion control; not the hybrid architecture",
        "encodings": rows,
    }
