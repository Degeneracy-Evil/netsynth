"""Adversarial local-layout lifetime and budget accounting, no partition optimization."""

from dataclasses import replace
from types import MappingProxyType

import pytest

from netsynth.forwarding import Locator
from netsynth.graph import Edge, Graph
from netsynth.scale4 import (
    ExecutionResult,
    PhysicalHop,
    RouteProgram,
    RouteQueryContext,
    execute_route_program,
)
from netsynth.scope_evolution import (
    FormationPolicy,
    RoutingScope,
    control_budget,
    hard_update_count,
    migration_cost,
)
from netsynth.scope_evolution_probe import exhaustive_valid, layouts, modular_graph, poor_graph, run_probe


def test_fourteen_criteria_reproducibly() -> None:
    probe = run_probe()
    criteria = probe["criteria"]
    assert isinstance(criteria, dict) and len(criteria) == 14
    assert all(value is True for value in criteria.values())
    assert run_probe() == probe


@pytest.mark.parametrize("case", ["overlap", "missing", "outside", "disconnected", "empty"])
def test_invalid_layout_cannot_change_live_scope_or_generation_floor(case: str) -> None:
    graph = Graph(set(range(4)), [Edge(0, 1), Edge(1, 2), Edge(2, 3)])
    scope = RoutingScope("local", (3,), graph.nodes, frozenset({0, 3}))
    old = scope.prepare(0, graph, (graph.nodes,))
    scope.activate(0)
    before = scope.export()
    match case:
        case "overlap":
            partition = (frozenset({0, 1}), frozenset({1, 2, 3}))
        case "missing":
            partition = (frozenset({0, 1}), frozenset({2}))
        case "outside":
            partition = (frozenset({0, 1}), frozenset({2, 3, 99}))
        case "disconnected":
            partition = (frozenset({0, 2}), frozenset({1, 3}))
        case _:
            partition = (graph.nodes, frozenset())
    with pytest.raises(ValueError):
        scope.prepare(1, graph, partition)
    assert scope._generation_floor == 0 and scope.layouts == {0: old}
    assert scope.preferred_generation == 0 and scope.export() == before


def test_coexistence_is_per_generation_and_label_reuse_never_aliases() -> None:
    graph = modular_graph()
    scope, old, new = layouts(graph, 5, "reuse", (4,))
    # Repartition with child labels reused; selector 0 now denotes a different attachment.
    scope.discard(1)
    reversed_partition = (frozenset(range(5, 10)), frozenset(range(5)))
    new = scope.prepare(2, graph, reversed_partition)
    old_locator = old.locator(0)
    new_locator = new.locator(5)
    assert old_locator.selector == new_locator.selector == 0
    assert old_locator.components[-1] == new_locator.components[-1] == 0
    assert old_locator != new_locator
    scope.activate(2)
    old.tree.validate(graph)
    new.tree.validate(graph)
    with pytest.raises(ValueError, match="generation"):
        new.compile(9, old_locator)
    result = scope.execute(graph, new.compile(9, new_locator), 100)
    assert isinstance(result, ExecutionResult) and result.path[-1] == 5
    result_old = scope.execute(graph, old.compile(9, old_locator), 100)
    assert isinstance(result_old, ExecutionResult) and result_old.path[-1] == 0
    with pytest.raises(ValueError, match="two layouts"):
        scope.prepare(3, graph, (graph.nodes,))
    scope.retire(0)
    with pytest.raises(ValueError, match="fresh"):
        scope.prepare(0, graph, (graph.nodes,))
    with pytest.raises(ValueError, match="fresh"):
        scope.prepare(1, graph, (graph.nodes,))


def test_prepared_activation_discard_and_retirement_are_not_global_epoch_operations() -> None:
    graph = modular_graph()
    scope, old, new = layouts(graph, 5, "one", (1,))
    other, other_old, _ = layouts(graph, 5, "other", (2,))
    route = old.compile(0, old.locator(9))
    with pytest.raises(ValueError, match="not active"):
        new.compile(0, new.locator(9))
    with pytest.raises(ValueError, match="non-preferred"):
        scope.retire(0)
    scope.activate(1)
    assert other.preferred_generation == 0 and other_old.phase == "active"
    assert other.execute(graph, other_old.compile(0, other_old.locator(9)), 100) != "stale_layout"
    with pytest.raises(ValueError, match="prepared"):
        scope.discard(1)
    scope.retire(0)
    assert scope.execute(graph, route, 100) == "stale_layout"
    with pytest.raises(ValueError, match="not active"):
        old.compile(0, old.locator(9))
    assert scope._generation_floor == other._generation_floor == 1
    assert scope.prefix != other.prefix


def test_retired_access_and_child_stps_fail_even_through_cached_frozen_executor_views() -> None:
    graph = modular_graph()
    scope, old, _new = layouts(graph, 5, "stale", (5,))
    route = old.compile(0, old.locator(9))
    cached = scope.registries()
    pathlet = old.child_btgs[0].pathlets[0]
    child_program = RouteProgram(old.locator(pathlet.egress), (pathlet.handle,))
    context = RouteQueryContext("child", pathlet.ingress)
    assert execute_route_program(graph, cached, MappingProxyType({}), child_program, context, 100).status == "delivered"
    scope.activate(1)
    scope.retire(0)
    assert (
        execute_route_program(graph, cached, route.access, route.program, route.context, 100).status
        == "missing_access_state"
    )
    assert (
        execute_route_program(graph, cached, MappingProxyType({}), child_program, context, 100).status
        == "stale_pathlet"
    )
    assert cached[pathlet.handle.owner_scope].lookup(pathlet.handle) is None
    assert not route.access


def test_disjoint_scope_regions_advance_generations_independently() -> None:
    graph = modular_graph()
    left_nodes, right_nodes = frozenset(range(5)), frozenset(range(5, 10))
    left = RoutingScope("left-region", (20,), left_nodes, frozenset({0, 4}))
    right = RoutingScope("right-region", (21,), right_nodes, frozenset({5, 9}))
    left.prepare(0, graph.induced(left_nodes), (left_nodes,))
    left.activate(0)
    right_layout = right.prepare(7, graph.induced(right_nodes), (right_nodes,))
    right.activate(7)
    right_contract = right.export()
    right_route = right_layout.compile(5, right_layout.locator(9))
    left.prepare(1, graph.induced(left_nodes), (frozenset({0, 1}), frozenset({2, 3, 4})))
    left.activate(1)
    left.retire(0)
    assert left.preferred_generation == 1 and right.preferred_generation == 7
    assert right.export() == right_contract
    result = right.execute(graph, right_route, 100)
    assert isinstance(result, ExecutionResult) and result.status == "delivered"


def test_grafting_new_locator_onto_old_access_program_cannot_alias() -> None:
    graph = modular_graph()
    scope, old, new = layouts(graph, 5, "graft", (22,))
    old_route = old.compile(0, old.locator(9))
    scope.activate(1)
    forged = replace(old_route, program=replace(old_route.program, destination=new.locator(9)))
    result = scope.execute(graph, forged, 100)
    assert isinstance(result, ExecutionResult) and result.status == "contract_violation"


def test_parent_contract_is_preserved_using_only_selected_layout_visible_actions() -> None:
    graph = modular_graph()
    scope, old, new = layouts(graph, 5, "stable", (6,))
    exported = scope.export()
    handles = tuple(item.handle for item in exported.pathlets)
    assert scope.parent_registry is not None
    old_realization = scope.parent_registry.lookup(handles[0])
    scope.activate(1)
    assert scope.export() == exported and scope.parent_hard_updates == 0
    assert scope.parent_registry is not None
    new_realization = scope.parent_registry.lookup(handles[0])
    assert old_realization is not None and new_realization is not None
    assert old_realization.realization != new_realization.realization
    new_child_handles = {item.handle for btg in new.child_btgs for item in btg.pathlets}
    for action in new_realization.realization:
        if isinstance(action, PhysicalHop):
            assert any({action.left, action.right} == {crossing.left, crossing.right} for crossing in new.crossings)
        else:
            assert action in new_child_handles
    scope.retire(old.generation)
    program = RouteProgram(
        Locator((77,), 0), (handles[0],)
    )  # Cached parent transit SEGMENT, not retired endpoint Locator.
    result = execute_route_program(
        graph,
        scope.registries(),
        MappingProxyType({}),
        program,
        RouteQueryContext("parent", exported.pathlets[0].ingress),
        100,
    )
    assert result.status == "delivered" and result.path[-1] == exported.pathlets[0].egress


def test_withdrawn_external_hard_handle_cannot_be_revived_by_view_rebinding() -> None:
    graph = modular_graph()
    scope, old, new = layouts(graph, 5, "withdrawn", (9,))
    assert scope.parent_registry is not None
    handle = scope.export().pathlets[0].handle
    scope.parent_registry.retire(handle)
    with pytest.raises(ValueError, match="revive"):
        scope.activate(1)
    assert old.phase == "active" and new.phase == "prepared"
    assert scope.preferred_generation == 0 and scope.parent_registry.lookup(handle) is None


def test_formation_and_runtime_need_only_declared_scope_local_topology(monkeypatch: pytest.MonkeyPatch) -> None:
    graph = modular_graph()
    members = frozenset(range(5))
    owner = RoutingScope("small-region", (11,), members, frozenset({0, 4}))
    with pytest.raises(ValueError, match="global topology"):
        owner.prepare(0, graph, (members,))
    local = graph.induced(members)
    generation = owner.prepare(0, local, (frozenset({0, 1}), frozenset({2, 3, 4})))

    def forbid_global_planner(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("parent/global path planner was used")

    monkeypatch.setattr(graph, "shortest_path", forbid_global_planner)
    monkeypatch.setattr(local, "shortest_path", forbid_global_planner)
    owner.activate(0)  # Only frozen abstract child-BTG resolution; no detailed/global path planner.
    route = generation.compile(0, generation.locator(4))
    result = owner.execute(graph, route, 100)  # Full physical graph is validator only.
    assert isinstance(result, ExecutionResult) and result.status == "delivered"
    assert not any("graph" in key or "members" in key for key in vars(generation.service))


def test_parent_visible_and_local_state_hard_churn_migration_are_all_charged() -> None:
    graph = modular_graph()
    scope, old, new = layouts(graph, 5, "accounting", (12,))
    exported = scope.export()
    old_budget, new_budget = control_budget(old, exported), control_budget(new, exported)
    assert old_budget.local_total_records == old_budget.maximum_controller_records
    assert new_budget.local_total_records > old_budget.local_total_records
    assert new_budget.root_local_records < old_budget.root_local_records
    assert new_budget.parent_visible_records == exported.persistent_records == 4
    assert new_budget.child_boundary_records == 4 and new_budget.child_btg_pathlet_records == 4
    migration = migration_cost(old, new, old_budget, new_budget, 2)
    assert migration.rebuilt_records == new_budget.local_total_records
    assert migration.renumbered_attachments == len(graph.nodes)
    assert migration.binding_publications == 4
    assert migration.overlap_records == old_budget.local_total_records + new_budget.local_total_records
    assert (
        migration.total
        == migration.rebuilt_records
        + migration.renumbered_attachments
        + migration.binding_publications
        + migration.overlap_records
    )
    soft = replace(exported, pathlets=tuple(replace(item, soft_metric=2) for item in exported.pathlets))
    assert hard_update_count(exported, soft) == 0
    hard = replace(exported, pathlets=exported.pathlets[1:])
    assert hard_update_count(exported, hard) == 1
    assert FormationPolicy().score(replace(new_budget, exported_hard_updates=1)) > FormationPolicy().score(new_budget)
    with pytest.raises(ValueError, match="non-negative"):
        migration_cost(old, new, old_budget, new_budget, -1)


def test_hysteresis_transition_cost_and_flat_merge_decisions() -> None:
    graph = modular_graph()
    scope, old, new = layouts(graph, 5, "policy", (13,))
    before, after = control_budget(old, scope.export()), control_budget(new, scope.export())
    migration = migration_cost(old, new, before, after, 2)
    policy = FormationPolicy()
    gain = policy.score(before) - policy.score(after)
    assert policy.evaluate(before, after, migration, (gain, gain, gain)) == "accept"
    assert policy.evaluate(before, after, migration, (gain,)) == "hysteresis"
    assert policy.evaluate(before, after, migration, (gain, 0, gain)) == "hysteresis"
    assert replace(policy, horizon=1).evaluate(before, after, migration, (gain, gain, gain)) == "migration_cost"
    assert (
        policy.evaluate(
            before,
            replace(before, maximum_controller_records=before.maximum_controller_records - 1),
            migration,
            (1, 1, 1),
        )
        != "accept"
    )
    poor = poor_graph()
    poor_scope, flat, split = layouts(poor, 3, "poor-policy", (14,))
    flat_budget, split_budget = control_budget(flat, poor_scope.export()), control_budget(split, poor_scope.export())
    cost = migration_cost(flat, split, flat_budget, split_budget, 2)
    gain = policy.score(flat_budget) - policy.score(split_budget)
    assert policy.evaluate(flat_budget, split_budget, cost, (gain, gain, gain)) != "accept"
    poor_scope.discard(1)  # Actual rejection leaves a flat live layout, not fake hierarchy.
    assert flat.flat and poor_scope.layouts == {0: flat} and poor_scope.preferred_generation == 0
    with pytest.raises(ValueError, match="positive"):
        FormationPolicy(persistent_samples=0)


def test_routes_can_leave_and_reenter_a_child_and_all_tiny_layouts_are_correct() -> None:
    graph = poor_graph()
    scope, old, new = layouts(graph, 3, "not-tree-routing", (15,))
    scope.activate(1)
    result = scope.execute(graph, new.compile(0, new.locator(1)), 100)
    assert isinstance(result, ExecutionResult) and result.path == (0, 3, 1)
    assert result.cost == 2 and graph.edge(0, 1) is not None
    assert exhaustive_valid(scope, graph, old) and exhaustive_valid(scope, graph, new)
    route = new.compile(0, new.locator(1))
    exhausted = scope.execute(graph, route, 0)
    assert isinstance(exhausted, ExecutionResult) and exhausted.status == "hop_budget_exhausted"
