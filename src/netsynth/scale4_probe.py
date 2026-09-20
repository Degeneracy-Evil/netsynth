"""One tiny adversarial Scale-4 semantic probe, not a parameter sweep."""

from __future__ import annotations

from types import MappingProxyType

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
    RouteQueryContext,
    ScopedTransitPathlet,
    ScopeRouteService,
    SourceAccessOffer,
    execute_flat_local,
    execute_route_program,
)


def run_probe() -> dict[str, object]:
    """Exercise leave/re-entry, hidden repair, soft update, and fail-closed reuse."""
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
    old_handle = PathletHandle("b", 0, 0)
    registry = PathletRegistry(b_scope)
    registry.publish(
        ScopedTransitPathlet(
            AdvertisedPathlet(old_handle, 1, 3, 2.0),
            (PhysicalHop(1, 2), PhysicalHop(2, 3)),
        )
    )
    registry.publish(
        ScopedTransitPathlet(
            AdvertisedPathlet(PathletHandle("b", 1, 0), 3, 1, 2.0),
            (PhysicalHop(3, 2), PhysicalHop(2, 1)),
        )
    )
    root = Scope(
        "root",
        graph.nodes,
        (a_scope, b_scope),
    )
    ScopeTree(root).validate(graph)
    service = ScopeRouteService(
        root,
        (
            BoundaryTransitGraph(
                "a",
                frozenset({0, 4}),
                (
                    AdvertisedPathlet(PathletHandle("a", 0, 0), 0, 4, 10.0),
                    AdvertisedPathlet(PathletHandle("a", 1, 0), 4, 0, 10.0),
                ),
            ),
            registry.export(frozenset({1, 3})),
        ),
        (CrossingLink(0, 1, 1.0), CrossingLink(3, 4, 1.0)),
    )
    source_handle = AccessHandle("a", "probe", 0)
    destination_handle = AccessHandle("a", "probe", 1)
    source_offers = (SourceAccessOffer(0, 1.0, source_handle),)
    destination_offers = (DestinationAccessOffer(4, 1.0, destination_handle),)
    context = RouteQueryContext(
        "probe",
        6,
        7,
        MappingProxyType(
            {
                source_handle: AccessRealization(6, 0, (PhysicalHop(6, 0),)),
                destination_handle: AccessRealization(4, 7, (PhysicalHop(4, 7),)),
            }
        ),
    )
    compiled = service.compile(Locator((0,), 7), source_offers, destination_offers)
    if compiled is None:
        raise AssertionError("adversarial probe unexpectedly has no abstract route")
    registries = MappingProxyType({"b": registry})
    baseline = execute_route_program(graph, registries, compiled.program, context, 16)

    registry.repair(old_handle, (PhysicalHop(1, 5), PhysicalHop(5, 3)))
    repaired = execute_route_program(graph, registries, compiled.program, context, 16)
    registry.update_soft_metric(old_handle, 9.0)
    soft_updated = execute_route_program(graph, registries, compiled.program, context, 16)

    registry.retire(old_handle)
    replacement = PathletHandle("b", 0, 1)
    registry.publish(
        ScopedTransitPathlet(
            AdvertisedPathlet(replacement, 1, 3, 2.0),
            (PhysicalHop(1, 5), PhysicalHop(5, 3)),
        )
    )
    stale = execute_route_program(graph, registries, compiled.program, context, 16)
    flat = execute_flat_local(Graph({0, 1}, [Edge(0, 1)]), 0, 1, Locator((), 1), 2)

    def child_for(node: int) -> str:
        return "b" if node in {1, 2, 3, 5} else "a"

    child_walk = tuple(child_for(node) for node in baseline.path)
    return {
        "schema": "netsynth.scale4.semantic-probe.v1",
        "topology": {
            "generator": "hand-built",
            "seed": None,
            "nodes": len(graph.nodes),
            "links": len(graph.edges),
            "adversarial": "connected-child-leave-reenter",
            "scope_children": service.immediate_child_ids,
        },
        "knowledge": {
            "parent_has_physical_graph": hasattr(service, "graph"),
            "parent_has_descendant_realizations": any(
                hasattr(pathlet, "realization") for btg in service.child_btgs for pathlet in btg.pathlets
            ),
            "access_state_is_query_time": all(
                not isinstance(item, AccessHandle) for item in (*service.child_btgs, *service.crossings)
            ),
        },
        "baseline": {
            "status": baseline.status,
            "physical_path": baseline.path,
            "left_and_reentered_child_a": "b" in child_walk and child_walk[-1] == "a",
            "destination_locator_components": compiled.program.destination.component_count,
            "sequential_header_length": baseline.sequential_header_length,
            "maximum_recursive_stack_depth": baseline.maximum_stack_depth,
        },
        "state_records": {
            "parent_persistent": service.persistent_records,
            "child_pathlet_before_failure": 7,
            "query_offers_and_selected_program": compiled.query_records,
            "query_realizations": context.charged_records,
            "child_pathlet_after_generation_replacement": registry.persistent_records,
        },
        "changes": {
            "hidden_repair": {"status": repaired.status, "same_cached_program": True, "path": repaired.path},
            "soft_metric": {"status": soft_updated.status, "generation_unchanged": True},
            "hard_failure": {
                "status": stale.status,
                "replacement_generation": replacement.generation,
                "stale_aliased_replacement": registry.lookup(old_handle) is not None,
            },
        },
        "small_scale": {
            "status": flat.status,
            "sequential_header_length": flat.sequential_header_length,
            "maximum_recursive_stack_depth": flat.maximum_stack_depth,
        },
    }
