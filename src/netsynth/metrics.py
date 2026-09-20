"""Consistent Phase-2 metrics over declared persistent information."""

from __future__ import annotations

import math
import statistics
from collections.abc import Iterable
from typing import Any

from netsynth.decomposition import Scope, ScopeTree
from netsynth.graph import Graph, Node
from netsynth.routing import RoutingSnapshot, RoutingStrategy, validate_path
from netsynth.summaries import SummaryBuild


def distribution(values: Iterable[float], percentiles: tuple[int, ...]) -> dict[str, float | int | None]:
    """Summarize measured values using nearest-rank percentiles."""
    ordered = sorted(values)
    if not ordered:
        return {"count": 0, "mean": None, **{f"p{value}": None for value in percentiles}, "max": None}
    result: dict[str, float | int | None] = {"count": len(ordered), "mean": statistics.fmean(ordered)}
    for percentile in percentiles:
        result[f"p{percentile}"] = ordered[max(0, math.ceil(percentile / 100 * len(ordered)) - 1)]
    result["max"] = ordered[-1]
    return result


def routing_state(snapshot: RoutingSnapshot, all_nodes: frozenset[Node]) -> dict[str, Any]:
    """Report object counts and normalized sizes by owner and semantic category."""
    categories = sorted({key[1] for key in snapshot.objects})
    by_category: dict[str, Any] = {}
    for category in categories:
        matching = [(key, value) for key, value in snapshot.objects.items() if key[1] == category]
        by_category[category] = {
            "object_total": len(matching),
            "normalized_size_total": sum(value.normalized_size for _key, value in matching),
        }
    object_counts = [sum(key[0] == node for key in snapshot.objects) for node in all_nodes]
    normalized_sizes = [
        sum(value.normalized_size for key, value in snapshot.objects.items() if key[0] == node) for node in all_nodes
    ]
    per_node_objects = distribution((float(value) for value in object_counts), (50, 95, 99))
    per_node_objects["median"] = per_node_objects["p50"]
    per_node_size = distribution((float(value) for value in normalized_sizes), (50, 95, 99))
    per_node_size["median"] = per_node_size["p50"]
    semantic_categories = {
        "data_plane_forwarding": {"forwarding_entry", "eligible_next_hop"},
        "potential_control": {"potential_record"},
        "attachment_control": {"attachment_advertisement"},
        "direct_neighbor_control": {"neighbor_link"},
        "local_detailed_topology": {"local_topology_node", "local_topology_link"},
        "global_detailed_topology": {"global_topology_node", "global_topology_link"},
        "remote_summary": set(categories).difference(
            {
                "forwarding_entry",
                "local_topology_node",
                "local_topology_link",
                "global_topology_node",
                "global_topology_link",
                "auxiliary_control",
                "eligible_next_hop",
                "potential_record",
                "attachment_advertisement",
                "neighbor_link",
            }
        ),
        "auxiliary_control": {"auxiliary_control"},
    }
    return {
        "object_total": len(snapshot.objects),
        "normalized_size_total": sum(value.normalized_size for value in snapshot.objects.values()),
        "per_node_objects": per_node_objects,
        "per_node_normalized_size": per_node_size,
        "by_category": by_category,
        "by_semantic_class": {
            name: {
                "object_total": sum(key[1] in members for key in snapshot.objects),
                "normalized_size_total": sum(
                    value.normalized_size for key, value in snapshot.objects.items() if key[1] in members
                ),
            }
            for name, members in semantic_categories.items()
        },
    }


def path_quality(
    graph: Graph,
    baseline: RoutingStrategy,
    candidate: RoutingStrategy,
    pairs: list[tuple[Node, Node]],
    tree: ScopeTree,
    *,
    sampled: bool,
) -> dict[str, Any]:
    """Measure weighted/hop stretch, additive overhead, and hierarchy groups."""
    groups: dict[str, list[tuple[Node, Node]]] = {"same_leaf": [], "sibling_scopes": [], "distant_scopes": []}
    for pair in pairs:
        groups[_relationship(tree, *pair)].append(pair)
    overall = _path_quality_for_pairs(graph, baseline, candidate, pairs)
    overall["sampled"] = sampled
    overall["by_relationship"] = {
        name: _path_quality_for_pairs(graph, baseline, candidate, group) for name, group in groups.items()
    }
    return overall


def _path_quality_for_pairs(
    graph: Graph, baseline: RoutingStrategy, candidate: RoutingStrategy, pairs: list[tuple[Node, Node]]
) -> dict[str, Any]:
    weighted_stretch: list[float] = []
    hop_stretch: list[float] = []
    additive: list[float] = []
    baseline_unreachable = 0
    route_failures = 0
    invalid = 0
    exact = 0
    for source, target in pairs:
        shortest = baseline.route(source, target)
        if shortest is None:
            baseline_unreachable += 1
            continue
        route = candidate.route(source, target)
        if route is None:
            route_failures += 1
            continue
        if not validate_path(graph, route, source, target):
            invalid += 1
            continue
        stretch = route.cost / shortest.cost
        weighted_stretch.append(stretch)
        hop_stretch.append((len(route.nodes) - 1) / (len(shortest.nodes) - 1))
        additive.append(route.cost - shortest.cost)
        if math.isclose(stretch, 1.0, rel_tol=1e-12, abs_tol=1e-12):
            exact += 1
    return {
        "requested_pair_count": len(pairs),
        "measured_pair_count": len(weighted_stretch),
        "baseline_unreachable_count": baseline_unreachable,
        "compressed_route_failure_count": route_failures,
        "invalid_route_count": invalid,
        "weighted_cost_stretch": distribution(weighted_stretch, (50, 95, 99)),
        "hop_count_stretch": distribution(hop_stretch, (50, 95, 99)),
        "additive_cost_overhead": distribution(additive, (50, 95, 99)),
        "exactly_shortest_fraction": exact / len(weighted_stretch) if weighted_stretch else None,
    }


def churn(before: RoutingSnapshot, after: RoutingSnapshot, all_nodes: frozenset[Node]) -> dict[str, Any]:
    """Count changes across every persistent category consumed by the strategy."""
    keys = before.objects.keys() | after.objects.keys()
    changed = {key for key in keys if before.objects.get(key) != after.objects.get(key)}
    active_after = {key[0] for key in after.objects}
    recipients = {key[0] for key in changed if key[0] in active_after}
    by_category = {
        category: sum(key[1] == category for key in changed) for category in sorted({key[1] for key in changed})
    }
    normalized_by_category = {
        category: sum(
            (after.objects.get(key) or before.objects[key]).normalized_size for key in changed if key[1] == category
        )
        for category in sorted({key[1] for key in changed})
    }
    forwarding = by_category.get("forwarding_entry", 0)
    local = sum(value for category, value in by_category.items() if category.startswith("local_topology_"))
    global_detail = sum(value for category, value in by_category.items() if category.startswith("global_topology_"))
    remote = len(changed) - forwarding - local - global_detail
    return {
        "changed_objects": len(changed),
        "changed_normalized_size": sum(normalized_by_category.values()),
        "changed_forwarding_objects": forwarding,
        "changed_local_detail_objects": local,
        "changed_global_detail_objects": global_detail,
        "changed_remote_summary_objects": remote,
        "changed_by_category": by_category,
        "changed_normalized_size_by_category": normalized_by_category,
        "changed_recipient_nodes": len(recipients),
        "changed_recipient_fraction": len(recipients) / len(all_nodes) if all_nodes else 0.0,
    }


def failure_locality(before: SummaryBuild, after: SummaryBuild) -> dict[str, Any]:
    """Follow compositional propagation using the same summaries routing consumes."""
    depths = _scope_depths(before.tree)
    reached = {
        identifier
        for identifier, view in before.views.items()
        if view.input_signature != after.views[identifier].input_signature
    }
    published = {
        identifier
        for identifier, view in before.views.items()
        if view.summary.signature != after.views[identifier].summary.signature
    }
    levels = sorted({depths[identifier] for identifier in reached})
    return {
        "recomputed_scope_count": len(reached),
        "recomputed_scopes": sorted(reached),
        "changed_published_summary_count": len(published),
        "changed_published_summaries": sorted(published),
        "reached_root_depths": levels,
        "reached_root": before.tree.root.identifier in reached,
        "highest_level_from_leaf": max(depths.values()) - min(levels) if levels else None,
    }


def _relationship(tree: ScopeTree, source: Node, target: Node) -> str:
    source_lineage = tree.lineage(source)
    target_lineage = tree.lineage(target)
    if source_lineage[-1] == target_lineage[-1]:
        return "same_leaf"
    common = 0
    while common < min(len(source_lineage), len(target_lineage)) and source_lineage[common] == target_lineage[common]:
        common += 1
    if common == len(source_lineage) - 1 and common == len(target_lineage) - 1:
        return "sibling_scopes"
    return "distant_scopes"


def _scope_depths(tree: ScopeTree) -> dict[str, int]:
    depths: dict[str, int] = {}

    def visit(scope: Scope, depth: int) -> None:
        depths[scope.identifier] = depth
        for child in scope.children:
            visit(child, depth + 1)

    visit(tree.root, 0)
    return depths
