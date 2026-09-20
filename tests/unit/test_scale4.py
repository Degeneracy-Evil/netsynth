"""Adversarial semantic validation for the minimal Scale-4 prototype."""

from types import MappingProxyType

import pytest

from netsynth.decomposition import Scope, ScopeTree
from netsynth.forwarding import Locator
from netsynth.graph import Edge, Graph
from netsynth.scale4 import (
    AccessHandle,
    AccessRealization,
    AdvertisedPathlet,
    BoundaryTransitGraph,
    CrossingLink,
    DestinationAccessOffer,
    PathletHandle,
    PathletRegistry,
    PhysicalHop,
    RouteProgram,
    RouteQueryContext,
    ScopedTransitPathlet,
    ScopeRouteService,
    SourceAccessOffer,
    execute_flat_local,
    execute_route_program,
    reachability_floor_holds,
)


def _leave_and_reenter_fixture() -> tuple[
    Graph,
    ScopeRouteService,
    PathletRegistry,
    tuple[SourceAccessOffer, ...],
    tuple[DestinationAccessOffer, ...],
    RouteQueryContext,
]:
    graph = Graph(
        set(range(8)),
        [
            Edge(0, 1),
            Edge(1, 2),
            Edge(2, 3),
            Edge(3, 4),
            Edge(0, 6),
            Edge(4, 7),
            Edge(1, 5),
            Edge(3, 5),
            Edge(0, 4, 10.0),
        ],
    )
    a_scope = Scope("a", frozenset({0, 4, 6, 7}))
    b_scope = Scope("b", frozenset({1, 2, 3, 5}))
    handle = PathletHandle("b", 0, 0)
    registry = PathletRegistry(b_scope)
    registry.publish(
        ScopedTransitPathlet(
            AdvertisedPathlet(handle, 1, 3, 2.0),
            (PhysicalHop(1, 2), PhysicalHop(2, 3)),
        )
    )
    registry.publish(
        ScopedTransitPathlet(
            AdvertisedPathlet(PathletHandle("b", 1, 0), 3, 1, 2.0),
            (PhysicalHop(3, 2), PhysicalHop(2, 1)),
        )
    )
    child_a = BoundaryTransitGraph(
        "a",
        frozenset({0, 4}),
        (
            AdvertisedPathlet(PathletHandle("a", 0, 0), 0, 4, 10.0),
            AdvertisedPathlet(PathletHandle("a", 1, 0), 4, 0, 10.0),
        ),
    )
    child_b = registry.export(frozenset({1, 3}))
    scope = Scope(
        "root",
        graph.nodes,
        (a_scope, b_scope),
    )
    ScopeTree(scope).validate(graph)
    service = ScopeRouteService(scope, (child_a, child_b), (CrossingLink(0, 1, 1.0), CrossingLink(3, 4, 1.0)))
    source_handle = AccessHandle("a", "q", 0)
    destination_handle = AccessHandle("a", "q", 1)
    source_offers = (SourceAccessOffer(0, 1.0, source_handle),)
    destination_offers = (DestinationAccessOffer(4, 1.0, destination_handle),)
    context = RouteQueryContext(
        "q",
        6,
        7,
        MappingProxyType(
            {
                source_handle: AccessRealization(6, 0, (PhysicalHop(6, 0),)),
                destination_handle: AccessRealization(4, 7, (PhysicalHop(4, 7),)),
            }
        ),
    )
    return graph, service, registry, source_offers, destination_offers, context


def test_pull_resolution_leaves_and_reenters_scope_without_topology_leak() -> None:
    graph, service, registry, source_offers, destination_offers, context = _leave_and_reenter_fixture()
    compiled = service.compile(Locator((0,), 7), source_offers, destination_offers)
    assert compiled is not None
    result = execute_route_program(graph, MappingProxyType({"b": registry}), compiled.program, context, hop_budget=16)
    assert result.status == "delivered"
    assert result.path == (6, 0, 1, 2, 3, 4, 7)
    assert result.sequential_header_length == 5
    assert result.maximum_stack_depth == 1
    assert compiled.query_records == 7
    assert context.charged_records == 5

    # The route starts in child A, transits child B, then re-enters A.
    child_visits = tuple("b" if node in {1, 2, 3, 5} else "a" for node in result.path)
    assert child_visits == ("a", "a", "b", "b", "b", "a", "a")

    # Parent state is exactly immediate-child contracts and crossings.
    assert not hasattr(service, "graph")
    assert not hasattr(service, "tree")
    assert all(not hasattr(pathlet, "realization") for btg in service.child_btgs for pathlet in btg.pathlets)
    assert all(
        not isinstance(value, AccessHandle) for value in (*service.child_btgs, *service.crossings, service.scope_id)
    )
    assert service.persistent_records == 13


def test_bottom_up_composition_executes_physical_hops_and_reports_two_header_dimensions() -> None:
    graph = Graph({0, 1, 2, 3}, [Edge(0, 1), Edge(1, 2), Edge(2, 3)])
    leaf_scope = Scope("leaf", frozenset({1, 2}))
    parent_scope = Scope(
        "parent",
        frozenset({0, 1, 2, 3}),
        (Scope("left", frozenset({0})), leaf_scope, Scope("right", frozenset({3}))),
    )
    leaf_handle = PathletHandle("leaf", 0, 0)
    parent_handle = PathletHandle("parent", 0, 0)
    leaf = PathletRegistry(leaf_scope)
    leaf.publish(ScopedTransitPathlet(AdvertisedPathlet(leaf_handle, 1, 2, 1.0), (PhysicalHop(1, 2),)))
    parent = PathletRegistry(parent_scope)
    parent.publish(
        ScopedTransitPathlet(
            AdvertisedPathlet(parent_handle, 0, 3, 3.0),
            (PhysicalHop(0, 1), leaf_handle, PhysicalHop(2, 3)),
        )
    )
    program = RouteProgram(Locator((0,), 3), (parent_handle,))
    context = RouteQueryContext("q", 0, 3, MappingProxyType({}))
    result = execute_route_program(
        graph,
        MappingProxyType({"leaf": leaf, "parent": parent}),
        program,
        context,
        hop_budget=3,
    )
    assert result.status == "delivered"
    assert result.path == (0, 1, 2, 3)
    assert result.sequential_header_length == 1
    assert result.maximum_stack_depth == 2
    assert result.physical_hops == 3


def test_persistent_pathlet_cannot_depend_on_peer_or_query_state() -> None:
    scope = Scope("owner", frozenset({0, 1}))
    registry = PathletRegistry(scope)
    advertisement = AdvertisedPathlet(PathletHandle("owner", 0, 0), 0, 1, 1.0)
    with pytest.raises(ValueError, match="proper descendant"):
        registry.publish(ScopedTransitPathlet(advertisement, (PathletHandle("peer", 0, 0),)))
    with pytest.raises(ValueError, match="query-time"):
        registry.publish(ScopedTransitPathlet(advertisement, (AccessHandle("owner", "q", 0),)))


def test_hidden_repair_and_soft_metric_change_preserve_cached_program() -> None:
    graph, service, registry, source_offers, destination_offers, context = _leave_and_reenter_fixture()
    compiled = service.compile(Locator((0,), 7), source_offers, destination_offers)
    assert compiled is not None
    handle = PathletHandle("b", 0, 0)
    cached = compiled.program

    registry.repair(handle, (PhysicalHop(1, 5), PhysicalHop(5, 3)))
    repaired = execute_route_program(graph, MappingProxyType({"b": registry}), cached, context, 16)
    assert repaired.status == "delivered"
    assert repaired.path == (6, 0, 1, 5, 3, 4, 7)
    assert handle in cached.dependencies

    registry.update_soft_metric(handle, 9.0)
    updated = registry.lookup(handle)
    assert updated is not None
    assert updated.advertisement.soft_metric == 9.0
    after_metric_change = execute_route_program(graph, MappingProxyType({"b": registry}), cached, context, 16)
    assert after_metric_change.status == "delivered"


def test_hard_failure_fails_closed_and_reused_slot_does_not_alias() -> None:
    graph, service, registry, source_offers, destination_offers, context = _leave_and_reenter_fixture()
    compiled = service.compile(Locator((0,), 7), source_offers, destination_offers)
    assert compiled is not None
    old = PathletHandle("b", 0, 0)
    registry.retire(old)
    replacement = PathletHandle("b", 0, 1)
    registry.publish(
        ScopedTransitPathlet(
            AdvertisedPathlet(replacement, 1, 3, 2.0),
            (PhysicalHop(1, 5), PhysicalHop(5, 3)),
        )
    )
    stale = execute_route_program(graph, MappingProxyType({"b": registry}), compiled.program, context, 16)
    assert stale.status == "stale_pathlet"
    assert stale.path == (6, 0, 1)
    assert registry.lookup(old) is None
    assert registry.lookup(replacement) is not None


def test_invalid_realization_and_missing_query_state_fail_explicitly() -> None:
    graph, service, registry, source_offers, destination_offers, context = _leave_and_reenter_fixture()
    compiled = service.compile(Locator((0,), 7), source_offers, destination_offers)
    assert compiled is not None
    handle = PathletHandle("b", 0, 0)
    registry.repair(handle, (PhysicalHop(1, 3),))
    invalid = execute_route_program(graph, MappingProxyType({"b": registry}), compiled.program, context, 16)
    assert invalid.status == "invalid_physical_hop"

    missing = RouteQueryContext("q", 6, 7, MappingProxyType({}))
    no_access = execute_route_program(graph, MappingProxyType({"b": registry}), compiled.program, missing, 16)
    assert no_access.status == "missing_access_state"


def test_reachability_floor_is_checked_at_child_without_exposing_topology() -> None:
    graph = Graph({0, 1, 2}, [Edge(0, 1), Edge(1, 2)])
    forward = AdvertisedPathlet(PathletHandle("child", 0, 0), 0, 2, 2.0)
    reverse = AdvertisedPathlet(PathletHandle("child", 1, 0), 2, 0, 2.0)
    complete = BoundaryTransitGraph("child", frozenset({0, 2}), (forward, reverse))
    incomplete = BoundaryTransitGraph("child", frozenset({0, 2}), (forward,))
    assert reachability_floor_holds(graph, graph.nodes, complete)
    assert not reachability_floor_holds(graph, graph.nodes, incomplete)


@pytest.mark.parametrize(
    ("graph", "source", "destination"),
    [
        (Graph({0, 1}, [Edge(0, 1)]), 0, 1),
        (Graph({0, 1, 2}, [Edge(0, 1), Edge(0, 2)]), 1, 2),
        (Graph({0, 1, 2, 3}, [Edge(0, 1), Edge(1, 2), Edge(2, 3), Edge(0, 3)]), 0, 2),
        (Graph({0, 1, 2, 3, 4}, [Edge(0, 1), Edge(1, 2), Edge(2, 3), Edge(3, 4), Edge(0, 4)]), 1, 3),
    ],
)
def test_scale_zero_through_three_need_no_scale4_state(graph: Graph, source: int, destination: int) -> None:
    result = execute_flat_local(graph, source, destination, Locator((), destination), hop_budget=8)
    assert result.status == "delivered"
    assert result.sequential_header_length == 0
    assert result.maximum_stack_depth == 0


def test_hop_budget_and_unresolvable_pull_are_explicit() -> None:
    graph, service, registry, source_offers, destination_offers, context = _leave_and_reenter_fixture()
    compiled = service.compile(Locator((0,), 7), source_offers, destination_offers)
    assert compiled is not None
    exhausted = execute_route_program(graph, MappingProxyType({"b": registry}), compiled.program, context, 2)
    assert exhausted.status == "hop_budget_exhausted"
    assert service.compile(Locator((0,), 7), source_offers, ()) is None
