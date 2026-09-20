"""Laminar scope decomposition and quotient-graph construction."""

from __future__ import annotations

import itertools
import random
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from netsynth.graph import Edge, Graph, Node


@dataclass(frozen=True)
class Scope:
    """One topology-compression scope with no administrative semantics."""

    identifier: str
    members: frozenset[Node]
    children: tuple[Scope, ...] = ()

    @property
    def is_leaf(self) -> bool:
        """Return whether this is a finest-resolution scope."""
        return not self.children


@dataclass(frozen=True)
class QuotientGraph:
    """A graph whose vertices are a scope's immediate child scopes."""

    scope_id: str
    graph: Graph
    child_by_node: dict[int, Scope]
    crossing_edges: dict[tuple[int, int], tuple[Edge, ...]]


@dataclass(frozen=True)
class ScopeTree:
    """A validated laminar decomposition over one physical graph."""

    root: Scope

    def validate(self, graph: Graph) -> None:
        """Validate coverage, laminar partitioning, and connected leaf interiors."""
        if self.root.members != graph.nodes:
            raise ValueError("root scope must cover the physical graph exactly")
        identifiers: set[str] = set()

        def visit(scope: Scope) -> None:
            if scope.identifier in identifiers:
                raise ValueError("scope identifiers must be unique")
            identifiers.add(scope.identifier)
            if scope.children:
                union = frozenset().union(*(child.members for child in scope.children))
                if union != scope.members or sum(len(child.members) for child in scope.children) != len(scope.members):
                    raise ValueError("scope children must be a disjoint exact partition")
                for child in scope.children:
                    visit(child)
            elif not graph.induced(scope.members).is_connected():
                raise ValueError("leaf scopes must induce connected physical subgraphs")

        visit(self.root)

    def scopes(self) -> tuple[Scope, ...]:
        """Return every scope in deterministic pre-order."""
        found: list[Scope] = []

        def visit(scope: Scope) -> None:
            found.append(scope)
            for child in scope.children:
                visit(child)

        visit(self.root)
        return tuple(found)

    def leaves(self) -> tuple[Scope, ...]:
        """Return finest-resolution scopes."""
        return tuple(scope for scope in self.scopes() if scope.is_leaf)

    def leaf_for(self, node: Node) -> Scope:
        """Return the finest scope containing node."""
        scope = self.root
        while scope.children:
            scope = next(child for child in scope.children if node in child.members)
        return scope

    def lineage(self, node: Node) -> tuple[Scope, ...]:
        """Return root-to-leaf scopes containing node."""
        lineage = [self.root]
        scope = self.root
        while scope.children:
            scope = next(child for child in scope.children if node in child.members)
            lineage.append(scope)
        return tuple(lineage)

    def quotients(self, graph: Graph) -> dict[str, QuotientGraph]:
        """Build one quotient graph for every non-leaf scope."""
        return {scope.identifier: build_quotient(graph, scope) for scope in self.scopes() if scope.children}

    def describe(self, graph: Graph) -> dict[str, Any]:
        """Describe hierarchy and quotient sizes for experiment output."""
        quotients = self.quotients(graph)
        depths: list[int] = []

        def visit(scope: Scope, depth: int) -> None:
            if scope.is_leaf:
                depths.extend([depth] * len(scope.members))
            for child in scope.children:
                visit(child, depth + 1)

        visit(self.root, 0)
        return {
            "scope_count": len(self.scopes()),
            "leaf_scope_count": len(self.leaves()),
            "node_depths": depths,
            "quotients": [
                {
                    "scope": identifier,
                    "nodes": len(quotient.graph.nodes),
                    "links": len(quotient.graph.edges),
                }
                for identifier, quotient in sorted(quotients.items())
            ],
        }


class DecompositionStrategy(Protocol):
    """Interchangeable scope-formation interface."""

    @property
    def parameters(self) -> Mapping[str, int | float | str]:
        """Return reproducibility metadata."""
        ...

    def decompose(self, graph: Graph) -> ScopeTree:
        """Build a scope hierarchy."""
        ...


@dataclass(frozen=True)
class BalancedConnectedDecomposition:
    """Recursively split connected scopes by deterministic two-source growth."""

    leaf_size: int = 8

    @property
    def parameters(self) -> dict[str, int | str]:
        """Return reproducibility metadata."""
        return {"name": "balanced_connected", "leaf_size": self.leaf_size, "fanout": 2}

    def decompose(self, graph: Graph) -> ScopeTree:
        """Build a binary hierarchy without assigning external meaning to scopes."""
        if self.leaf_size < 1:
            raise ValueError("leaf_size must be positive")
        if not graph.is_connected():
            raise ValueError("decomposition currently requires a connected graph")

        def split(members: frozenset[Node], identifier: str) -> Scope:
            if len(members) <= self.leaf_size:
                return Scope(identifier, members)
            left, right = _connected_bisection(graph, members)
            return Scope(identifier, members, (split(left, f"{identifier}.0"), split(right, f"{identifier}.1")))

        tree = ScopeTree(split(graph.nodes, "s"))
        tree.validate(graph)
        return tree


def _connected_bisection(graph: Graph, members: frozenset[Node]) -> tuple[frozenset[Node], frozenset[Node]]:
    subgraph = graph.induced(members)
    first = min(members)
    first_distances = _hop_distances(subgraph, first)
    second = max(members, key=lambda node: (first_distances[node], node))
    second_distances = _hop_distances(subgraph, second)
    preferred_left = {node for node in members if (first_distances[node], node) <= (second_distances[node], -node)}
    # Assign through simultaneous connected growth, using distance preference only as a tie-break.
    target = len(members) // 2
    left = {first}
    right = {second}
    unassigned = set(members).difference((first, second))
    queues = (deque([first]), deque([second]))
    while unassigned:
        progressed = False
        for index, (owned, queue) in enumerate(((left, queues[0]), (right, queues[1]))):
            if not queue:
                continue
            node = queue.popleft()
            for neighbor, _edge in subgraph.neighbors(node):
                if neighbor not in unassigned:
                    continue
                wants_left = neighbor in preferred_left
                if (index == 0 and wants_left and len(left) < target) or index == 1 or len(left) >= target:
                    owned.add(neighbor)
                    unassigned.remove(neighbor)
                    queue.append(neighbor)
                    progressed = True
        if not progressed:
            # A frontier may prefer the other side; preserve connectivity by accepting its smallest frontier node.
            candidates = [
                (neighbor, index)
                for index, owned in enumerate((left, right))
                for node in owned
                for neighbor, _edge in subgraph.neighbors(node)
                if neighbor in unassigned
            ]
            neighbor, index = min(candidates)
            (left if index == 0 else right).add(neighbor)
            unassigned.remove(neighbor)
            queues[index].append(neighbor)
    if not subgraph.induced(frozenset(left)).is_connected() or not subgraph.induced(frozenset(right)).is_connected():
        return _tree_cut(subgraph, members)
    return frozenset(left), frozenset(right)


def _tree_cut(graph: Graph, members: frozenset[Node]) -> tuple[frozenset[Node], frozenset[Node]]:
    """Fallback connected split by cutting a balanced edge of a DFS spanning tree."""
    root = min(members)
    parent: dict[Node, Node | None] = {root: None}
    order = [root]
    for node in order:
        for neighbor, _edge in graph.neighbors(node):
            if neighbor not in parent:
                parent[neighbor] = node
                order.append(neighbor)
    descendants: dict[Node, set[Node]] = {node: {node} for node in order}
    for node in reversed(order[1:]):
        ancestor = parent[node]
        if ancestor is not None:
            descendants[ancestor].update(descendants[node])
    candidate = min(order[1:], key=lambda node: (abs(len(members) - 2 * len(descendants[node])), node))
    left = frozenset(descendants[candidate])
    return left, members.difference(left)


def _hop_distances(graph: Graph, source: Node) -> dict[Node, int]:
    unreachable = len(graph.nodes) + 1
    distances = dict.fromkeys(graph.nodes, unreachable)
    distances[source] = 0
    queue = deque([source])
    while queue:
        node = queue.popleft()
        for neighbor, _edge in graph.neighbors(node):
            if distances[neighbor] == unreachable:
                distances[neighbor] = distances[node] + 1
                queue.append(neighbor)
    return distances


def build_quotient(graph: Graph, scope: Scope) -> QuotientGraph:
    """Contract immediate children, retaining every physical crossing link."""
    child_index = {node: index for index, child in enumerate(scope.children) for node in child.members}
    crossings: dict[tuple[int, int], list[Edge]] = {}
    for edge in graph.edges:
        left_child = child_index.get(edge.left)
        right_child = child_index.get(edge.right)
        if left_child is None or right_child is None or left_child == right_child:
            continue
        key = (min(left_child, right_child), max(left_child, right_child))
        crossings.setdefault(key, []).append(edge)
    quotient_edges = [
        Edge(left, right, min(edge.cost for edge in physical), sum(edge.capacity for edge in physical))
        for (left, right), physical in sorted(crossings.items())
    ]
    return QuotientGraph(
        scope.identifier,
        Graph(set(range(len(scope.children))), quotient_edges),
        dict(enumerate(scope.children)),
        {key: tuple(sorted(edges)) for key, edges in crossings.items()},
    )


class MetricAwareDecomposition:
    """Bounded global-distance research oracle for low-distortion connected Scopes."""

    def __init__(
        self,
        leaf_size: int = 8,
        *,
        candidate_limit: int = 64,
        boundary_weight: float = 0.25,
        imbalance_weight: float = 0.1,
        seed: int = 0,
    ) -> None:
        if leaf_size < 1 or candidate_limit < 1:
            raise ValueError("leaf_size and candidate_limit must be positive")
        if boundary_weight < 0 or imbalance_weight < 0:
            raise ValueError("objective weights cannot be negative")
        self.leaf_size = leaf_size
        self.candidate_limit = candidate_limit
        self.boundary_weight = boundary_weight
        self.imbalance_weight = imbalance_weight
        self.seed = seed
        self.construction_stats: dict[str, int] = {}

    @property
    def parameters(self) -> dict[str, int | float | str]:
        """Expose the oracle's explicit multi-objective search inputs."""
        return {
            "name": "metric_aware_global_distance_oracle",
            "leaf_size": self.leaf_size,
            "candidate_limit_per_scope": self.candidate_limit,
            "boundary_weight": self.boundary_weight,
            "imbalance_weight": self.imbalance_weight,
            "seed": self.seed,
            "formation_model": "centralized_research_oracle_not_deployable",
        }

    def decompose(self, graph: Graph) -> ScopeTree:
        """Choose connected recursive splits using measured weighted distortion."""
        if not graph.is_connected():
            raise ValueError("decomposition currently requires a connected graph")
        global_distances, global_work = _weighted_pair_distances(graph, graph.nodes)
        counters = {
            "candidate_splits_evaluated": 0,
            "candidate_splits_rejected": 0,
            "shortest_path_computations": global_work,
        }

        def split(members: frozenset[Node], identifier: str) -> Scope:
            if len(members) <= self.leaf_size:
                return Scope(identifier, members)
            candidates = _metric_candidates(graph, members, self.candidate_limit, self.seed, counters)
            control = _connected_bisection(graph, members)
            if control not in candidates and (control[1], control[0]) not in candidates:
                candidates.append(control)
            scored: list[
                tuple[tuple[float, float, float, tuple[Node, ...]], tuple[frozenset[Node], frozenset[Node]]]
            ] = []
            for left, right in candidates:
                counters["candidate_splits_evaluated"] += 1
                if not graph.induced(left).is_connected() or not graph.induced(right).is_connected():
                    counters["candidate_splits_rejected"] += 1
                    continue
                distortion, work = _split_distortion(graph, (left, right), global_distances)
                counters["shortest_path_computations"] += work
                boundary_ratio = _split_boundary_count(graph, left, right) / len(members)
                imbalance = abs(len(left) - len(right)) / len(members)
                objective = distortion + self.boundary_weight * boundary_ratio + self.imbalance_weight * imbalance
                scored.append(((objective, distortion, boundary_ratio, tuple(sorted(left))), (left, right)))
            if not scored:
                raise ValueError("metric-aware oracle found no connected split")
            left, right = min(scored)[1]
            return Scope(identifier, members, (split(left, f"{identifier}.0"), split(right, f"{identifier}.1")))

        tree = ScopeTree(split(graph.nodes, "s"))
        tree.validate(graph)
        self.construction_stats = {**counters, "global_pair_count": len(global_distances)}
        return tree


@dataclass(frozen=True)
class PoorConnectedDecomposition:
    """Deterministic unbalanced connected hierarchy used as a negative control."""

    leaf_size: int = 8

    @property
    def parameters(self) -> dict[str, int | str]:
        return {"name": "poor_connected_peel", "leaf_size": self.leaf_size}

    def decompose(self, graph: Graph) -> ScopeTree:
        if self.leaf_size < 1 or not graph.is_connected():
            raise ValueError("poor decomposition requires a connected graph and positive leaf size")

        def split(members: frozenset[Node], identifier: str) -> Scope:
            if len(members) <= self.leaf_size:
                return Scope(identifier, members)
            peeled = next(node for node in sorted(members) if graph.induced(members.difference((node,))).is_connected())
            left, right = frozenset((peeled,)), members.difference((peeled,))
            return Scope(identifier, members, (Scope(f"{identifier}.0", left), split(right, f"{identifier}.1")))

        tree = ScopeTree(split(graph.nodes, "s"))
        tree.validate(graph)
        return tree


def _metric_candidates(
    graph: Graph,
    members: frozenset[Node],
    limit: int,
    seed: int,
    counters: dict[str, int],
) -> list[tuple[frozenset[Node], frozenset[Node]]]:
    pairs = list(itertools.combinations(sorted(members), 2))
    if len(pairs) > limit:
        pairs = random.Random(seed + sum(members) + len(members)).sample(pairs, limit)
    subgraph = graph.induced(members)
    cache: dict[Node, dict[Node, float]] = {}
    candidates: list[tuple[frozenset[Node], frozenset[Node]]] = []
    for first, second in sorted(pairs):
        for source in (first, second):
            if source not in cache:
                cache[source] = {}
                for target in members:
                    path = subgraph.shortest_path(source, target)
                    counters["shortest_path_computations"] += 1
                    if path is not None:
                        cache[source][target] = path.cost
        left = frozenset(node for node in members if (cache[first][node], node) <= (cache[second][node], -node))
        right = members.difference(left)
        if left and right and (left, right) not in candidates and (right, left) not in candidates:
            candidates.append((left, right))
    return candidates


def _weighted_pair_distances(graph: Graph, members: frozenset[Node]) -> tuple[dict[tuple[Node, Node], float], int]:
    distances: dict[tuple[Node, Node], float] = {}
    work = 0
    for left, right in itertools.combinations(sorted(members), 2):
        path = graph.shortest_path(left, right)
        work += 1
        if path is not None:
            distances[(left, right)] = path.cost
    return distances, work


def _split_distortion(
    graph: Graph,
    children: tuple[frozenset[Node], frozenset[Node]],
    global_distances: dict[tuple[Node, Node], float],
) -> tuple[float, int]:
    maximum = 1.0
    work = 0
    for members in children:
        induced = graph.induced(members)
        for left, right in itertools.combinations(sorted(members), 2):
            path = induced.shortest_path(left, right)
            work += 1
            if path is not None:
                maximum = max(maximum, path.cost / global_distances[(left, right)])
    return maximum, work


def _split_boundary_count(graph: Graph, left: frozenset[Node], right: frozenset[Node]) -> int:
    return len(
        {
            node
            for edge in graph.edges
            for node, other in ((edge.left, edge.right), (edge.right, edge.left))
            if (node in left and other in right) or (node in right and other in left)
        }
    )
