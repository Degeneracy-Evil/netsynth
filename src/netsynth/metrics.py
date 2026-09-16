"""Metric definitions for phase-1 routing experiments."""

from __future__ import annotations

import math
import statistics
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from netsynth.decomposition import Scope, ScopeTree
from netsynth.graph import Graph, Node
from netsynth.routing import RoutingSnapshot, RoutingStrategy, validate_path


def distribution(values: Iterable[float], percentiles: tuple[int, ...]) -> dict[str, float | int | None]:
    """Summarize measured values using nearest-rank percentiles."""
    ordered = sorted(values)
    if not ordered:
        return {"count": 0, "mean": None, **{f"p{percentile}": None for percentile in percentiles}, "max": None}
    result: dict[str, float | int | None] = {"count": len(ordered), "mean": statistics.fmean(ordered)}
    for percentile in percentiles:
        rank = max(0, math.ceil(percentile / 100 * len(ordered)) - 1)
        result[f"p{percentile}"] = ordered[rank]
    result["max"] = ordered[-1]
    return result


def routing_state(snapshot: RoutingSnapshot, all_nodes: frozenset[Node]) -> dict[str, Any]:
    """Measure per-node and total explicit routing entries."""
    counts = snapshot.per_node_counts(all_nodes)
    totals = [local + aggregate for local, aggregate in counts.values()]
    per_node = distribution((float(value) for value in totals), (50, 95, 99))
    per_node["median"] = per_node["p50"]
    return {
        "per_node": per_node,
        "total": sum(totals),
        "local_detail_total": sum(local for local, _aggregate in counts.values()),
        "aggregate_total": sum(aggregate for _local, aggregate in counts.values()),
    }


def path_stretch(
    graph: Graph,
    baseline: RoutingStrategy,
    compressed: RoutingStrategy,
    pairs: list[tuple[Node, Node]],
    *,
    sampled: bool,
) -> dict[str, Any]:
    """Compare valid compressed routes against same-graph shortest paths."""
    stretches: list[float] = []
    unreachable_baseline = 0
    compressed_failures = 0
    invalid_routes = 0
    exact = 0
    for source, target in pairs:
        shortest = baseline.route(graph, source, target)
        if shortest is None:
            unreachable_baseline += 1
            continue
        route = compressed.route(graph, source, target)
        if route is None:
            compressed_failures += 1
            continue
        if not validate_path(graph, route, source, target):
            invalid_routes += 1
            continue
        stretch = route.cost / shortest.cost
        stretches.append(stretch)
        if math.isclose(stretch, 1.0, rel_tol=1e-12, abs_tol=1e-12):
            exact += 1
    return {
        "sampled": sampled,
        "requested_pair_count": len(pairs),
        "measured_pair_count": len(stretches),
        "baseline_unreachable_count": unreachable_baseline,
        "compressed_route_failure_count": compressed_failures,
        "invalid_route_count": invalid_routes,
        "stretch": distribution(stretches, (50, 95, 99)),
        "exactly_one_fraction": exact / len(stretches) if stretches else None,
    }


def churn(before: RoutingSnapshot, after: RoutingSnapshot, all_nodes: frozenset[Node]) -> dict[str, Any]:
    """Count changed explicit state objects without treating CPU work as control traffic."""
    keys = before.entries.keys() | after.entries.keys()
    changed = {key for key in keys if before.entries.get(key) != after.entries.get(key)}
    changed_nodes = {key[0] for key in changed}
    changed_aggregate = changed.intersection(before.aggregate_keys | after.aggregate_keys)
    return {
        "changed_objects": len(changed),
        "changed_aggregate_objects": len(changed_aggregate),
        "changed_nodes": len(changed_nodes),
        "changed_node_fraction": len(changed_nodes) / len(all_nodes) if all_nodes else 0.0,
    }


@dataclass(frozen=True)
class ScopeSummary:
    """Externally visible boundary links and intra-scope boundary distances."""

    crossing_links: tuple[tuple[int, int, float], ...]
    boundary_distances: tuple[tuple[int, int, float | None], ...]


def scope_summaries(graph: Graph, tree: ScopeTree, reference_graph: Graph) -> dict[str, ScopeSummary]:
    """Compute summaries against stable reference boundary identities."""
    return {scope.identifier: _scope_summary(graph, scope, reference_graph) for scope in tree.scopes()}


def failure_locality(before: Graph, after: Graph, tree: ScopeTree) -> dict[str, Any]:
    """Report which hierarchy levels see an externally visible summary change."""
    old = scope_summaries(before, tree, before)
    new = scope_summaries(after, tree, before)
    depths = _scope_depths(tree)
    parents = _scope_parents(tree)
    changed = {identifier for identifier in old if old[identifier] != new[identifier]}
    # A changed summary is produced by its scope and consumed one level up. Propagation
    # stops there unless that parent's own externally visible summary also changes.
    reached = changed | {parent for identifier in changed if (parent := parents[identifier]) is not None}
    reached_levels = sorted({depths[identifier] for identifier in reached})
    highest_level_from_leaf = max(depths.values()) - min(reached_levels) if reached_levels else None
    return {
        "changed_scope_count": len(changed),
        "changed_scopes": sorted(changed),
        "reached_scope_count": len(reached),
        "reached_scopes": sorted(reached),
        "reached_root_depths": reached_levels,
        "reached_root": tree.root.identifier in reached,
        "highest_level_from_leaf": highest_level_from_leaf,
    }


def _scope_summary(graph: Graph, scope: Scope, reference: Graph) -> ScopeSummary:
    reference_crossing = [
        edge for edge in reference.edges if (edge.left in scope.members) != (edge.right in scope.members)
    ]
    boundary = sorted(
        {node for edge in reference_crossing for node in (edge.left, edge.right) if node in scope.members}
    )
    current_crossing = tuple(
        (edge.left, edge.right, edge.cost)
        for edge in graph.edges
        if (edge.left in scope.members) != (edge.right in scope.members)
    )
    induced = graph.induced(scope.members)
    distances: list[tuple[int, int, float | None]] = []
    for index, left in enumerate(boundary):
        for right in boundary[index + 1 :]:
            path = induced.shortest_path(left, right)
            distances.append((left, right, path.cost if path is not None else None))
    return ScopeSummary(current_crossing, tuple(distances))


def _scope_depths(tree: ScopeTree) -> dict[str, int]:
    depths: dict[str, int] = {}

    def visit(scope: Scope, depth: int) -> None:
        depths[scope.identifier] = depth
        for child in scope.children:
            visit(child, depth + 1)

    visit(tree.root, 0)
    return depths


def _scope_parents(tree: ScopeTree) -> dict[str, str | None]:
    parents: dict[str, str | None] = {tree.root.identifier: None}

    def visit(scope: Scope) -> None:
        for child in scope.children:
            parents[child.identifier] = scope.identifier
            visit(child)

    visit(tree.root)
    return parents
