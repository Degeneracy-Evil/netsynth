"""Small dependency-free undirected weighted graph model."""

from __future__ import annotations

from dataclasses import dataclass
from heapq import heappop, heappush
from math import inf
from typing import Any

Node = int


@dataclass(frozen=True, order=True)
class Edge:
    """An undirected physical link and its experiment metadata."""

    left: Node
    right: Node
    cost: float = 1.0
    capacity: float = 1.0

    def __post_init__(self) -> None:
        if self.left == self.right:
            raise ValueError("self-links are not supported")
        if self.left > self.right:
            old_left, old_right = self.left, self.right
            object.__setattr__(self, "left", old_right)
            object.__setattr__(self, "right", old_left)
        if self.cost <= 0 or self.capacity <= 0:
            raise ValueError("link cost and capacity must be positive")

    @property
    def key(self) -> tuple[Node, Node]:
        """Return the canonical endpoint pair."""
        return (self.left, self.right)


@dataclass(frozen=True)
class Path:
    """A physical-node path and its total link cost."""

    nodes: tuple[Node, ...]
    cost: float


class Graph:
    """A deterministic undirected graph; node integers have no protocol meaning."""

    def __init__(self, nodes: set[Node], edges: list[Edge]) -> None:
        self._nodes = frozenset(nodes)
        adjacency: dict[Node, dict[Node, Edge]] = {node: {} for node in nodes}
        canonical: dict[tuple[Node, Node], Edge] = {}
        for edge in edges:
            if edge.left not in nodes or edge.right not in nodes:
                raise ValueError("link endpoint is not in the graph")
            previous = canonical.get(edge.key)
            if previous is None or edge.cost < previous.cost:
                canonical[edge.key] = edge
        for edge in canonical.values():
            adjacency[edge.left][edge.right] = edge
            adjacency[edge.right][edge.left] = edge
        self._adjacency = adjacency
        self._edges = tuple(sorted(canonical.values()))

    @property
    def nodes(self) -> frozenset[Node]:
        """Return physical forwarding nodes."""
        return self._nodes

    @property
    def edges(self) -> tuple[Edge, ...]:
        """Return physical links in canonical order."""
        return self._edges

    def neighbors(self, node: Node) -> tuple[tuple[Node, Edge], ...]:
        """Return neighbors in stable order."""
        return tuple(sorted(self._adjacency[node].items()))

    def edge(self, left: Node, right: Node) -> Edge | None:
        """Return a physical edge if it exists."""
        return self._adjacency.get(left, {}).get(right)

    def induced(self, members: frozenset[Node] | set[Node]) -> Graph:
        """Return the subgraph induced by members still present in this graph."""
        kept = self._nodes.intersection(members)
        return Graph(set(kept), [edge for edge in self._edges if edge.left in kept and edge.right in kept])

    def without(
        self, *, nodes: frozenset[Node] = frozenset(), edges: frozenset[tuple[Node, Node]] = frozenset()
    ) -> Graph:
        """Return a graph snapshot with selected physical objects down."""
        normalized = {tuple(sorted(pair)) for pair in edges}
        kept_nodes = self._nodes.difference(nodes)
        kept_edges = [
            edge
            for edge in self._edges
            if edge.left in kept_nodes and edge.right in kept_nodes and edge.key not in normalized
        ]
        return Graph(set(kept_nodes), kept_edges)

    def shortest_path(self, source: Node, target: Node, allowed: frozenset[Node] | None = None) -> Path | None:
        """Compute a deterministic minimum-cost path, optionally inside a scope."""
        if source not in self._nodes or target not in self._nodes:
            return None
        permitted = self._nodes if allowed is None else self._nodes.intersection(allowed)
        if source not in permitted or target not in permitted:
            return None
        distances: dict[Node, float] = {source: 0.0}
        paths: dict[Node, tuple[Node, ...]] = {source: (source,)}
        queue: list[tuple[float, tuple[Node, ...], Node]] = [(0.0, (source,), source)]
        while queue:
            distance, path, node = heappop(queue)
            if distance != distances.get(node) or path != paths.get(node):
                continue
            if node == target:
                return Path(path, distance)
            for neighbor, edge in self.neighbors(node):
                if neighbor not in permitted:
                    continue
                candidate = distance + edge.cost
                candidate_path = (*path, neighbor)
                if candidate < distances.get(neighbor, inf) or (
                    candidate == distances.get(neighbor) and candidate_path < paths[neighbor]
                ):
                    distances[neighbor] = candidate
                    paths[neighbor] = candidate_path
                    heappush(queue, (candidate, candidate_path, neighbor))
        return None

    def is_connected(self) -> bool:
        """Return whether every present node is mutually reachable."""
        if not self._nodes:
            return True
        start = min(self._nodes)
        seen = {start}
        pending = [start]
        while pending:
            node = pending.pop()
            for neighbor, _edge in self.neighbors(node):
                if neighbor not in seen:
                    seen.add(neighbor)
                    pending.append(neighbor)
        return seen == set(self._nodes)

    def to_dict(self) -> dict[str, Any]:
        """Return a machine-readable graph description."""
        return {
            "nodes": sorted(self._nodes),
            "links": [
                {"left": edge.left, "right": edge.right, "cost": edge.cost, "capacity": edge.capacity}
                for edge in self._edges
            ],
        }
