"""Adversarial semantic validation for the minimal Scale-4 prototype."""

from types import MappingProxyType

import pytest

from netsynth.decomposition import Scope, ScopeTree
from netsynth.forwarding import Locator
from netsynth.graph import Edge, Graph
from netsynth.scale4 import (
    AccessHandle,
    AccessRealization,
    AccessRegistry,
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
    AccessRegistry,
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
    registry = PathletRegistry(
        "b",
        frozenset(
            {
                PhysicalHop(1, 2),
                PhysicalHop(2, 3),
                PhysicalHop(3, 2),
                PhysicalHop(2, 1),
                PhysicalHop(1, 5),
                PhysicalHop(5, 3),
            }
        ),
    )
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
    service = ScopeRouteService(
        "root",
        ("a", "b"),
        {0: "a", 4: "a", 1: "b", 3: "b"},
        (child_a, child_b),
        (CrossingLink(0, 1, 1.0), CrossingLink(3, 4, 1.0)),
    )
    source_handle = AccessHandle("a", "q", 0)
    destination_handle = AccessHandle("a", "q", 1)
    source_offers = (SourceAccessOffer(0, 1.0, source_handle),)
    destination_offers = (DestinationAccessOffer(4, 1.0, destination_handle),)
    access_registry = AccessRegistry(
        "a",
        "q",
        frozenset({0, 4}),
        frozenset({PhysicalHop(6, 0), PhysicalHop(4, 7)}),
    )
    access_registry.publish_source(source_offers[0], AccessRealization(6, 0, (PhysicalHop(6, 0),)))
    access_registry.publish_destination(destination_offers[0], AccessRealization(4, 7, (PhysicalHop(4, 7),)))
    context = RouteQueryContext("q", 6)
    return graph, service, registry, access_registry, source_offers, destination_offers, context


def test_pull_resolution_leaves_and_reenters_scope_without_topology_leak() -> None:
    graph, service, registry, access, source_offers, destination_offers, context = _leave_and_reenter_fixture()
    compiled = service.compile("q", Locator((0,), 7), source_offers, destination_offers)
    assert compiled is not None
    result = execute_route_program(
        graph,
        MappingProxyType({"b": registry}),
        MappingProxyType({"a": access}),
        compiled.program,
        context,
        hop_budget=16,
    )
    assert result.status == "delivered"
    assert result.path == (6, 0, 1, 2, 3, 4, 7)
    assert result.sequential_header_length == 5
    assert result.maximum_stack_depth == 1
    assert compiled.query_records == 7
    assert context.charged_records == 1
    assert access.charged_records == 5

    # The route starts in child A, transits child B, then re-enters A.
    child_visits = tuple("b" if node in {1, 2, 3, 5} else "a" for node in result.path)
    assert child_visits == ("a", "a", "b", "b", "b", "a", "a")

    # Parent state is exactly immediate-child contracts and crossings.
    assert not hasattr(service, "graph")
    assert not hasattr(service, "tree")
    assert not hasattr(service, "members")
    assert all(not hasattr(pathlet, "realization") for btg in service.child_btgs for pathlet in btg.pathlets)
    assert all(
        not isinstance(value, AccessHandle) for value in (*service.child_btgs, *service.crossings, service.scope_id)
    )
    assert service.persistent_records == 13


def test_bottom_up_composition_executes_physical_hops_and_reports_two_header_dimensions() -> None:
    graph = Graph({0, 1, 2, 3}, [Edge(0, 1), Edge(1, 2), Edge(2, 3)])
    leaf_handle = PathletHandle("leaf", 0, 0)
    parent_handle = PathletHandle("parent", 0, 0)
    leaf = PathletRegistry("leaf", frozenset({PhysicalHop(1, 2)}))
    leaf.publish(ScopedTransitPathlet(AdvertisedPathlet(leaf_handle, 1, 2, 1.0), (PhysicalHop(1, 2),)))
    leaf_btg = leaf.export(frozenset({1, 2}))
    parent = PathletRegistry(
        "parent",
        frozenset({PhysicalHop(0, 1), PhysicalHop(2, 3)}),
        (leaf_btg,),
    )
    parent.publish(
        ScopedTransitPathlet(
            AdvertisedPathlet(parent_handle, 0, 3, 3.0),
            (PhysicalHop(0, 1), leaf_handle, PhysicalHop(2, 3)),
        )
    )
    program = RouteProgram(Locator((0,), 3), (parent_handle,))
    context = RouteQueryContext("q", 0)
    result = execute_route_program(
        graph,
        MappingProxyType({"leaf": leaf, "parent": parent}),
        MappingProxyType({}),
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
    registry = PathletRegistry("owner", frozenset({PhysicalHop(0, 1)}))
    advertisement = AdvertisedPathlet(PathletHandle("owner", 0, 0), 0, 1, 1.0)
    with pytest.raises(ValueError, match="immediate child"):
        registry.publish(ScopedTransitPathlet(advertisement, (PathletHandle("peer", 0, 0),)))
    with pytest.raises(ValueError, match="AccessHandles"):
        registry.publish(ScopedTransitPathlet(advertisement, (AccessHandle("owner", "q", 0),)))


def test_ancestor_rejects_descendant_interior_hops_and_grandchild_handles() -> None:
    grandchild_handle = PathletHandle("grandchild", 0, 0)
    grandchild_btg = BoundaryTransitGraph(
        "grandchild",
        frozenset({1, 2}),
        (AdvertisedPathlet(grandchild_handle, 1, 2, 1.0),),
    )
    child_handle = PathletHandle("child", 0, 0)
    child = PathletRegistry(
        "child",
        frozenset({PhysicalHop(0, 1), PhysicalHop(2, 3)}),
        (grandchild_btg,),
    )
    child.publish(
        ScopedTransitPathlet(
            AdvertisedPathlet(child_handle, 0, 3, 3.0),
            (PhysicalHop(0, 1), grandchild_handle, PhysicalHop(2, 3)),
        )
    )
    parent = PathletRegistry(
        "parent",
        frozenset({PhysicalHop(4, 0), PhysicalHop(3, 5)}),
        (child.export(frozenset({0, 3})),),
    )
    with pytest.raises(ValueError, match="not visible"):
        parent.publish(
            ScopedTransitPathlet(
                AdvertisedPathlet(PathletHandle("parent", 0, 0), 1, 2, 1.0),
                (PhysicalHop(1, 2),),
            )
        )
    with pytest.raises(ValueError, match="immediate child"):
        parent.publish(
            ScopedTransitPathlet(
                AdvertisedPathlet(PathletHandle("parent", 0, 0), 1, 2, 1.0),
                (grandchild_handle,),
            )
        )
    assert not hasattr(parent, "graph")
    assert not hasattr(parent, "members")


def test_publish_and_repair_reject_noncontinuous_or_unowned_realizations() -> None:
    handle = PathletHandle("leaf", 0, 0)
    advertised = AdvertisedPathlet(handle, 0, 3, 3.0)
    registry = PathletRegistry(
        "leaf",
        frozenset({PhysicalHop(0, 1), PhysicalHop(1, 2), PhysicalHop(2, 3)}),
    )
    with pytest.raises(ValueError, match="continuous"):
        registry.publish(ScopedTransitPathlet(advertised, (PhysicalHop(0, 1), PhysicalHop(2, 3))))
    with pytest.raises(ValueError, match="advertised egress"):
        registry.publish(ScopedTransitPathlet(advertised, (PhysicalHop(0, 1),)))
    with pytest.raises(ValueError, match="not visible"):
        registry.publish(ScopedTransitPathlet(advertised, (PhysicalHop(0, 3),)))

    valid = (PhysicalHop(0, 1), PhysicalHop(1, 2), PhysicalHop(2, 3))
    registry.publish(ScopedTransitPathlet(advertised, valid))
    with pytest.raises(ValueError, match="continuous"):
        registry.repair(handle, (PhysicalHop(0, 1), PhysicalHop(2, 3)))
    active = registry.lookup(handle)
    assert active is not None and active.realization == valid


def test_access_realizations_are_owner_local_opaque_and_consistent() -> None:
    physical = frozenset({PhysicalHop(6, 0), PhysicalHop(4, 7)})
    registry = AccessRegistry("a", "q", frozenset({0, 4}), physical)
    source = SourceAccessOffer(0, 1.0, AccessHandle("a", "q", 0))
    destination = DestinationAccessOffer(4, 1.0, AccessHandle("a", "q", 1))
    registry.publish_source(source, AccessRealization(6, 0, (PhysicalHop(6, 0),)))
    registry.publish_destination(destination, AccessRealization(4, 7, (PhysicalHop(4, 7),)))

    assert not hasattr(source, "realization")
    assert not hasattr(destination, "realization")
    assert not hasattr(RouteQueryContext("q", 6), "realizations")
    assert registry.lookup(source.handle) is not None

    with pytest.raises(ValueError, match="owner"):
        registry.publish_source(
            SourceAccessOffer(0, 1.0, AccessHandle("b", "q", 2)),
            AccessRealization(6, 0, (PhysicalHop(6, 0),)),
        )
    with pytest.raises(ValueError, match="query"):
        registry.publish_source(
            SourceAccessOffer(0, 1.0, AccessHandle("a", "other", 2)),
            AccessRealization(6, 0, (PhysicalHop(6, 0),)),
        )
    with pytest.raises(ValueError, match="boundary"):
        registry.publish_source(
            SourceAccessOffer(9, 1.0, AccessHandle("a", "q", 2)),
            AccessRealization(6, 9, (PhysicalHop(6, 0),)),
        )


def test_route_service_validates_only_boundary_ownership_and_offer_metadata() -> None:
    left = BoundaryTransitGraph("left", frozenset({0}), ())
    right = BoundaryTransitGraph("right", frozenset({1}), ())
    service = ScopeRouteService("root", ("left", "right"), {0: "left", 1: "right"}, (left, right), ())
    assert not hasattr(service, "scope")
    assert not hasattr(service, "child_by_node")
    assert dict(service.boundary_owner) == {0: "left", 1: "right"}

    with pytest.raises(ValueError, match="boundary ownership"):
        ScopeRouteService("root", ("left", "right"), {0: "left"}, (left, right), ())
    with pytest.raises(ValueError, match="owned boundaries"):
        ScopeRouteService(
            "root",
            ("left", "right"),
            {0: "left", 1: "right"},
            (left, right),
            (CrossingLink(0, 9, 1.0),),
        )
    with pytest.raises(ValueError, match="query identity"):
        service.compile(
            "q",
            Locator((0,), 0),
            (SourceAccessOffer(0, 0.0, AccessHandle("left", "other", 0)),),
            (),
        )
    with pytest.raises(ValueError, match="not owned"):
        service.compile(
            "q",
            Locator((0,), 0),
            (SourceAccessOffer(0, 0.0, AccessHandle("right", "q", 0)),),
            (),
        )


def test_generation_history_is_bounded_by_slots_not_retirements() -> None:
    registry = PathletRegistry("leaf", frozenset({PhysicalHop(0, 1)}))
    for generation in range(100):
        handle = PathletHandle("leaf", 0, generation)
        registry.publish(ScopedTransitPathlet(AdvertisedPathlet(handle, 0, 1, 1.0), (PhysicalHop(0, 1),)))
        registry.retire(handle)
    active = PathletHandle("leaf", 0, 100)
    registry.publish(ScopedTransitPathlet(AdvertisedPathlet(active, 0, 1, 1.0), (PhysicalHop(0, 1),)))
    assert registry.generation_record_count == 1
    assert registry.persistent_records == 4
    assert registry.lookup(PathletHandle("leaf", 0, 0)) is None
    registry.retire(active)
    with pytest.raises(ValueError, match="monotonically"):
        registry.publish(
            ScopedTransitPathlet(
                AdvertisedPathlet(PathletHandle("leaf", 0, 99), 0, 1, 1.0),
                (PhysicalHop(0, 1),),
            )
        )


def test_hidden_repair_and_soft_metric_change_preserve_cached_program() -> None:
    graph, service, registry, access, source_offers, destination_offers, context = _leave_and_reenter_fixture()
    compiled = service.compile("q", Locator((0,), 7), source_offers, destination_offers)
    assert compiled is not None
    handle = PathletHandle("b", 0, 0)
    cached = compiled.program

    registry.repair(handle, (PhysicalHop(1, 5), PhysicalHop(5, 3)))
    repaired = execute_route_program(
        graph, MappingProxyType({"b": registry}), MappingProxyType({"a": access}), cached, context, 16
    )
    assert repaired.status == "delivered"
    assert repaired.path == (6, 0, 1, 5, 3, 4, 7)
    assert handle in cached.dependencies

    registry.update_soft_metric(handle, 9.0)
    updated = registry.lookup(handle)
    assert updated is not None
    assert updated.advertisement.soft_metric == 9.0
    after_metric_change = execute_route_program(
        graph, MappingProxyType({"b": registry}), MappingProxyType({"a": access}), cached, context, 16
    )
    assert after_metric_change.status == "delivered"


def test_hard_failure_fails_closed_and_reused_slot_does_not_alias() -> None:
    graph, service, registry, access, source_offers, destination_offers, context = _leave_and_reenter_fixture()
    compiled = service.compile("q", Locator((0,), 7), source_offers, destination_offers)
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
    stale = execute_route_program(
        graph,
        MappingProxyType({"b": registry}),
        MappingProxyType({"a": access}),
        compiled.program,
        context,
        16,
    )
    assert stale.status == "stale_pathlet"
    assert stale.path == (6, 0, 1)
    assert registry.lookup(old) is None
    assert registry.lookup(replacement) is not None


def test_invalid_realization_and_missing_query_state_fail_explicitly() -> None:
    graph, service, registry, access, source_offers, destination_offers, context = _leave_and_reenter_fixture()
    compiled = service.compile("q", Locator((0,), 7), source_offers, destination_offers)
    assert compiled is not None
    failed_graph = graph.without(edges=frozenset({(1, 2)}))
    invalid = execute_route_program(
        failed_graph,
        MappingProxyType({"b": registry}),
        MappingProxyType({"a": access}),
        compiled.program,
        context,
        16,
    )
    assert invalid.status == "invalid_physical_hop"

    no_access = execute_route_program(
        graph, MappingProxyType({"b": registry}), MappingProxyType({}), compiled.program, context, 16
    )
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
    graph, service, registry, access, source_offers, destination_offers, context = _leave_and_reenter_fixture()
    compiled = service.compile("q", Locator((0,), 7), source_offers, destination_offers)
    assert compiled is not None
    exhausted = execute_route_program(
        graph,
        MappingProxyType({"b": registry}),
        MappingProxyType({"a": access}),
        compiled.program,
        context,
        2,
    )
    assert exhausted.status == "hop_budget_exhausted"
    assert service.compile("q", Locator((0,), 7), source_offers, ()) is None
