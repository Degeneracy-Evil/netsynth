"""Flat and recursively compressed routing models."""

from __future__ import annotations

from dataclasses import dataclass
from math import inf
from typing import Protocol

from netsynth.decomposition import QuotientGraph, Scope, ScopeTree
from netsynth.graph import Graph, Node, Path

StateKey = tuple[Node, str, str]
StateValue = tuple[int | None, float | None]


@dataclass(frozen=True)
class RoutingSnapshot:
    """Explicit routing/control objects charged to nodes."""

    entries: dict[StateKey, StateValue]
    local_keys: frozenset[StateKey]
    aggregate_keys: frozenset[StateKey]

    def per_node_counts(self, all_nodes: frozenset[Node]) -> dict[Node, tuple[int, int]]:
        """Return local and aggregate counts for every physical node."""
        return {
            node: (
                sum(key[0] == node for key in self.local_keys),
                sum(key[0] == node for key in self.aggregate_keys),
            )
            for node in all_nodes
        }


class RoutingStrategy(Protocol):
    """Common route and state interface for experiment comparison."""

    @property
    def name(self) -> str:
        """Return the strategy name recorded in results."""
        ...

    def route(self, graph: Graph, source: Node, target: Node) -> Path | None:
        """Compute a physical route."""
        ...

    def snapshot(self, graph: Graph) -> RoutingSnapshot:
        """Materialize the routing state charged by this model."""
        ...


class FlatRouting:
    """Full-topology shortest-path baseline."""

    name = "flat_full_knowledge"

    def route(self, graph: Graph, source: Node, target: Node) -> Path | None:
        """Return a physical shortest path."""
        return graph.shortest_path(source, target)

    def snapshot(self, graph: Graph) -> RoutingSnapshot:
        """Charge one destination-oriented entry per ordered node pair."""
        entries: dict[StateKey, StateValue] = {}
        for source in sorted(graph.nodes):
            for target in sorted(graph.nodes):
                if source == target:
                    continue
                path = graph.shortest_path(source, target)
                entries[(source, "destination", str(target))] = (
                    path.nodes[1] if path is not None else None,
                    path.cost if path is not None else None,
                )
        keys = frozenset(entries)
        return RoutingSnapshot(entries, keys, frozenset())


class CompressedRouting:
    """Conservative hierarchy-guided routing over child quotient graphs."""

    name = "recursive_scope_quotient"

    def __init__(self, tree: ScopeTree) -> None:
        self._tree = tree

    def route(self, graph: Graph, source: Node, target: Node) -> Path | None:
        """Expand a quotient path recursively into a physical route."""
        if source not in graph.nodes or target not in graph.nodes:
            return None
        return self._route_in_scope(graph, self._tree.root, source, target)

    def _route_in_scope(self, graph: Graph, scope: Scope, source: Node, target: Node) -> Path | None:
        if source == target:
            return Path((source,), 0.0)
        if scope.is_leaf:
            return graph.shortest_path(source, target, scope.members)
        source_index = next(index for index, child in enumerate(scope.children) if source in child.members)
        target_index = next(index for index, child in enumerate(scope.children) if target in child.members)
        if source_index == target_index:
            return self._route_in_scope(graph, scope.children[source_index], source, target)
        quotient = self._quotient(graph, scope)
        coarse = quotient.graph.shortest_path(source_index, target_index)
        if coarse is None:
            return None
        result = [source]
        cost = 0.0
        current = source
        for left_index, right_index in zip(coarse.nodes, coarse.nodes[1:], strict=False):
            key = (min(left_index, right_index), max(left_index, right_index))
            candidates = quotient.crossing_edges[key]
            crossing = min(candidates, key=lambda edge: (edge.cost, edge.left, edge.right))
            left_scope = scope.children[left_index]
            if crossing.left in left_scope.members:
                exit_node, entry_node = crossing.left, crossing.right
            else:
                exit_node, entry_node = crossing.right, crossing.left
            internal = self._route_in_scope(graph, left_scope, current, exit_node)
            if internal is None:
                return None
            result.extend(internal.nodes[1:])
            result.append(entry_node)
            cost += internal.cost + crossing.cost
            current = entry_node
        destination_scope = scope.children[target_index]
        final = self._route_in_scope(graph, destination_scope, current, target)
        if final is None:
            return None
        result.extend(final.nodes[1:])
        cost += final.cost
        if len(set(result)) != len(result):
            # Hierarchy-guided paths should be simple; expose a failed route rather than hide a loop.
            return None
        return Path(tuple(result), cost)

    def snapshot(self, graph: Graph) -> RoutingSnapshot:
        """Charge local destinations and remote aggregate targets at each ancestor."""
        entries: dict[StateKey, StateValue] = {}
        local_keys: set[StateKey] = set()
        aggregate_keys: set[StateKey] = set()
        quotients = self._tree.quotients(graph)
        for node in sorted(graph.nodes):
            leaf = self._tree.leaf_for(node)
            leaf_graph = graph.induced(leaf.members)
            for target in sorted(leaf.members.intersection(graph.nodes)):
                if target == node:
                    continue
                key = (node, "local", str(target))
                path = leaf_graph.shortest_path(node, target)
                entries[key] = (path.nodes[1] if path is not None else None, path.cost if path is not None else None)
                local_keys.add(key)
            for scope in self._tree.lineage(node):
                if scope.is_leaf:
                    continue
                own_index = next(index for index, child in enumerate(scope.children) if node in child.members)
                quotient = quotients[scope.identifier]
                for target_index, child in quotient.child_by_node.items():
                    if target_index == own_index:
                        continue
                    key = (node, f"aggregate:{scope.identifier}", child.identifier)
                    path = quotient.graph.shortest_path(own_index, target_index)
                    entries[key] = (
                        path.nodes[1] if path is not None else None,
                        path.cost if path is not None else None,
                    )
                    aggregate_keys.add(key)
        return RoutingSnapshot(entries, frozenset(local_keys), frozenset(aggregate_keys))

    @staticmethod
    def _quotient(graph: Graph, scope: Scope) -> QuotientGraph:
        from netsynth.decomposition import build_quotient

        return build_quotient(graph, scope)


def validate_path(graph: Graph, path: Path, source: Node, target: Node) -> bool:
    """Check endpoints, physical adjacency, simplicity, and reported cost."""
    if not path.nodes or path.nodes[0] != source or path.nodes[-1] != target:
        return False
    if len(set(path.nodes)) != len(path.nodes):
        return False
    cost = 0.0
    for left, right in zip(path.nodes, path.nodes[1:], strict=False):
        edge = graph.edge(left, right)
        if edge is None:
            return False
        cost += edge.cost
    return abs(cost - path.cost) < max(1.0, abs(cost)) * 1e-12 and path.cost < inf
