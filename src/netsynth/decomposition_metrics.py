"""Metric distortion and boundary measurements for Scope decompositions."""

from __future__ import annotations

import itertools
from typing import Any

from netsynth.decomposition import Scope, ScopeTree
from netsynth.graph import Graph, Node
from netsynth.metrics import distribution


def decomposition_quality(graph: Graph, tree: ScopeTree) -> dict[str, Any]:
    """Compare induced-Scope distances with global weighted distances."""
    global_distances = _distances(graph, graph.nodes)
    scopes: list[dict[str, Any]] = []
    ratios_by_depth: dict[int, list[float]] = {}
    worst: tuple[float, str, tuple[Node, Node] | None] = (1.0, tree.root.identifier, None)

    def visit(scope: Scope, depth: int) -> None:
        nonlocal worst
        induced = graph.induced(scope.members)
        ratios: list[float] = []
        worst_pair: tuple[Node, Node] | None = None
        worst_ratio = 1.0
        for pair in itertools.combinations(sorted(scope.members), 2):
            internal = induced.shortest_path(*pair)
            if internal is None:
                continue
            ratio = internal.cost / global_distances[pair]
            ratios.append(ratio)
            ratios_by_depth.setdefault(depth, []).append(ratio)
            if ratio > worst_ratio:
                worst_ratio, worst_pair = ratio, pair
        boundary = _boundary_nodes(graph, scope)
        crossing = _crossing_links(graph, scope)
        scopes.append(
            {
                "scope": scope.identifier,
                "depth": depth,
                "member_count": len(scope.members),
                "child_count": len(scope.children),
                "boundary_interface_count": len(boundary),
                "crossing_link_count": crossing,
                "boundary_member_ratio": len(boundary) / len(scope.members),
                "distortion": _ratio_distribution(ratios),
                "worst_pair": list(worst_pair) if worst_pair is not None else None,
            }
        )
        if worst_ratio > worst[0]:
            worst = (worst_ratio, scope.identifier, worst_pair)
        for child in scope.children:
            visit(child, depth + 1)

    visit(tree.root, 0)
    all_ratios = [ratio for values in ratios_by_depth.values() for ratio in values]
    return {
        "aggregate_distortion": _ratio_distribution(all_ratios),
        "distortion_by_depth": {
            str(depth): _ratio_distribution(values) for depth, values in sorted(ratios_by_depth.items())
        },
        "boundary_interfaces": distribution(
            (float(scope["boundary_interface_count"]) for scope in scopes), (50, 95, 99)
        ),
        "crossing_links": distribution((float(scope["crossing_link_count"]) for scope in scopes), (50, 95, 99)),
        "worst_scope": {"ratio": worst[0], "scope": worst[1], "pair": list(worst[2]) if worst[2] else None},
        "scopes": scopes,
    }


def _distances(graph: Graph, members: frozenset[Node]) -> dict[tuple[Node, Node], float]:
    result: dict[tuple[Node, Node], float] = {}
    for pair in itertools.combinations(sorted(members), 2):
        path = graph.shortest_path(*pair)
        if path is not None:
            result[pair] = path.cost
    return result


def _ratio_distribution(values: list[float]) -> dict[str, float | int | None]:
    result = distribution(values, (50, 95, 99))
    result["exactly_one_fraction"] = sum(abs(value - 1.0) < 1e-12 for value in values) / len(values) if values else None
    return result


def _boundary_nodes(graph: Graph, scope: Scope) -> set[Node]:
    return {
        node
        for edge in graph.edges
        for node, other in ((edge.left, edge.right), (edge.right, edge.left))
        if node in scope.members and other not in scope.members
    }


def _crossing_links(graph: Graph, scope: Scope) -> int:
    return sum((edge.left in scope.members) != (edge.right in scope.members) for edge in graph.edges)
