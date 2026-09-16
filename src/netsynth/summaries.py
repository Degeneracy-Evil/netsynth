"""Composable routing-summary information budgets for Phase 2."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from netsynth.decomposition import Scope, ScopeTree
from netsynth.graph import Edge, Graph, Node

SummaryLevel = Literal["s0", "s1", "s2", "s3"]


@dataclass(frozen=True)
class SummaryConfig:
    """One declared routing-summary information budget."""

    level: SummaryLevel
    landmark_count: int = 0
    bundle_representatives: int = 2

    def __post_init__(self) -> None:
        if self.level == "s2" and self.landmark_count < 1:
            raise ValueError("S2 requires at least one landmark")
        if self.bundle_representatives < 1:
            raise ValueError("bundle_representatives must be positive")

    @property
    def name(self) -> str:
        """Return a stable strategy label."""
        return f"s2_k{self.landmark_count}" if self.level == "s2" else self.level

    def to_dict(self) -> dict[str, int | str]:
        """Return reproducibility metadata."""
        result: dict[str, int | str] = {"level": self.level, "name": self.name}
        if self.level == "s1":
            result["bundle_representatives"] = self.bundle_representatives
        if self.level == "s2":
            result["landmark_count"] = self.landmark_count
        return result


@dataclass(frozen=True, order=True)
class SummaryDistance:
    """A persistent advertised distance; None means currently unreachable."""

    identifier: str
    left: Node
    right: Node
    cost: float | None
    category: Literal["boundary_distance", "landmark_distance", "attachment"]


@dataclass(frozen=True, order=True)
class CrossingObject:
    """Persistent crossing-link or boundary-bundle state consumed at one scope."""

    identifier: str
    category: Literal["crossing_link", "boundary_bundle"]
    value: tuple[object, ...]
    normalized_size: int
    usable_edges: tuple[Edge, ...]


@dataclass(frozen=True)
class PublishedSummary:
    """The only information about a scope visible to its parent."""

    scope_id: str
    boundary_nodes: tuple[Node, ...]
    portals: tuple[Node, ...]
    distances: tuple[SummaryDistance, ...]

    @property
    def signature(self) -> tuple[object, ...]:
        """Return all externally visible persistent values."""
        return (self.boundary_nodes, self.portals, self.distances)

    def usable_edges(self) -> tuple[Edge, ...]:
        """Return the abstract edges a parent may consume."""
        return tuple(
            Edge(record.left, record.right, record.cost)
            for record in self.distances
            if record.cost is not None and record.left != record.right
        )


@dataclass(frozen=True)
class ScopeView:
    """Declared inputs and published output for one scope."""

    scope: Scope
    summary: PublishedSummary
    crossings: tuple[CrossingObject, ...]
    quotient_adjacencies: tuple[tuple[str, tuple[object, ...]], ...]
    input_signature: tuple[object, ...]


@dataclass(frozen=True)
class SummaryBuild:
    """A complete bottom-up summary construction for one graph snapshot."""

    config: SummaryConfig
    graph: Graph
    reference_graph: Graph
    tree: ScopeTree
    views: dict[str, ScopeView]


class SummaryBuilder:
    """Construct summaries without reading hidden descendant topology."""

    def __init__(self, tree: ScopeTree, reference_graph: Graph, config: SummaryConfig) -> None:
        self._tree = tree
        self._reference = reference_graph
        self._config = config
        self._parents = _parents(tree)

    def build(self, graph: Graph) -> SummaryBuild:
        """Build every summary in post-order from declared inputs only."""
        views: dict[str, ScopeView] = {}

        def visit(scope: Scope) -> None:
            for child in scope.children:
                visit(child)
            crossings = self._crossings(scope, graph)
            available = self._available_graph(scope, graph, views, crossings)
            summary = self._publish(scope, available, graph)
            if scope.is_leaf:
                input_signature: tuple[object, ...] = (
                    tuple(sorted(graph.nodes.intersection(scope.members))),
                    tuple(graph.induced(scope.members).edges),
                )
            else:
                input_signature = (
                    tuple((child.identifier, views[child.identifier].summary.signature) for child in scope.children),
                    tuple((record.identifier, record.value) for record in crossings),
                )
            views[scope.identifier] = ScopeView(
                scope,
                summary,
                crossings,
                self._quotient_adjacencies(scope, crossings),
                input_signature,
            )

        visit(self._tree.root)
        return SummaryBuild(self._config, graph, self._reference, self._tree, views)

    def _available_graph(
        self,
        scope: Scope,
        graph: Graph,
        views: dict[str, ScopeView],
        crossings: tuple[CrossingObject, ...],
    ) -> Graph:
        if scope.is_leaf:
            return graph.induced(scope.members)
        edges = [edge for child in scope.children for edge in views[child.identifier].summary.usable_edges()]
        edges.extend(edge for crossing in crossings for edge in crossing.usable_edges)
        return Graph(set(graph.nodes.intersection(scope.members)), edges)

    def _publish(self, scope: Scope, available: Graph, graph: Graph) -> PublishedSummary:
        boundary = self._boundary_nodes(scope)
        present_boundary = tuple(node for node in boundary if node in graph.nodes)
        if self._config.level == "s0" or not boundary:
            return PublishedSummary(scope.identifier, boundary, (), ())
        if self._config.level == "s1":
            portals = self._bundle_portals(scope)
            distances = _pair_distances(available, portals, "boundary_distance")
            return PublishedSummary(scope.identifier, boundary, portals, distances)
        if self._config.level == "s2":
            portals = _select_landmarks(boundary, self._config.landmark_count)
            s2_distances = list(_pair_distances(available, portals, "landmark_distance"))
            for node in boundary:
                if node in portals:
                    continue
                choices = [
                    (path.cost, portal)
                    for portal in portals
                    if (path := available.shortest_path(node, portal)) is not None
                ]
                if choices:
                    cost, portal = min(choices)
                else:
                    portal, cost = portals[0], None
                s2_distances.append(SummaryDistance(f"attach:{node}", node, portal, cost, "attachment"))
            return PublishedSummary(scope.identifier, boundary, portals, tuple(sorted(s2_distances)))
        s3_distances = _pair_distances(available, boundary, "boundary_distance")
        return PublishedSummary(scope.identifier, boundary, present_boundary, s3_distances)

    def _boundary_nodes(self, scope: Scope) -> tuple[Node, ...]:
        return tuple(
            sorted(
                {
                    node
                    for edge in self._reference.edges
                    for node in (edge.left, edge.right)
                    if node in scope.members and ((edge.left in scope.members) != (edge.right in scope.members))
                }
            )
        )

    def _bundle_portals(self, scope: Scope) -> tuple[Node, ...]:
        parent = self._parents[scope.identifier]
        if parent is None:
            return ()
        siblings = {node: child.identifier for child in parent.children if child != scope for node in child.members}
        bundles: dict[str, list[tuple[float, Node, Node]]] = {}
        for edge in self._reference.edges:
            if edge.left in scope.members and edge.right in siblings:
                bundles.setdefault(siblings[edge.right], []).append((edge.cost, edge.left, edge.right))
            elif edge.right in scope.members and edge.left in siblings:
                bundles.setdefault(siblings[edge.left], []).append((edge.cost, edge.right, edge.left))
        portals: set[Node] = set()
        for records in bundles.values():
            selected: list[Node] = []
            for _cost, inside, _outside in sorted(records):
                if inside not in selected:
                    selected.append(inside)
                if len(selected) == self._config.bundle_representatives:
                    break
            portals.update(selected)
        return tuple(sorted(portals))

    def _crossings(self, scope: Scope, graph: Graph) -> tuple[CrossingObject, ...]:
        if scope.is_leaf:
            return ()
        child_index = {node: index for index, child in enumerate(scope.children) for node in child.members}
        reference_groups: dict[tuple[int, int], list[Edge]] = {}
        current_by_key = {edge.key: edge for edge in graph.edges}
        for edge in self._reference.edges:
            left_index = child_index.get(edge.left)
            right_index = child_index.get(edge.right)
            if left_index is None or right_index is None or left_index == right_index:
                continue
            key = (min(left_index, right_index), max(left_index, right_index))
            reference_groups.setdefault(key, []).append(edge)
        if self._config.level != "s1":
            records: list[CrossingObject] = []
            for edges in reference_groups.values():
                for edge in sorted(edges):
                    current = current_by_key.get(edge.key)
                    records.append(
                        CrossingObject(
                            f"link:{edge.left}:{edge.right}",
                            "crossing_link",
                            (edge.left in graph.nodes, edge.right in graph.nodes, current.cost if current else None),
                            4,
                            (current,) if current is not None else (),
                        )
                    )
            return tuple(records)
        bundles: list[CrossingObject] = []
        for (left_index, right_index), reference_edges in sorted(reference_groups.items()):
            representatives = tuple(sorted(reference_edges, key=lambda edge: (edge.cost, edge.left, edge.right)))[
                : self._config.bundle_representatives
            ]
            usable = tuple(current_by_key[edge.key] for edge in representatives if edge.key in current_by_key)
            current_all = [current_by_key[edge.key] for edge in reference_edges if edge.key in current_by_key]
            value: tuple[object, ...] = (
                len(current_all),
                min((edge.cost for edge in current_all), default=None),
                tuple(
                    (edge.left, edge.right, edge.cost if edge.key in current_by_key else None)
                    for edge in representatives
                ),
            )
            bundles.append(
                CrossingObject(
                    f"bundle:{left_index}:{right_index}",
                    "boundary_bundle",
                    value,
                    4 + 4 * len(representatives),
                    usable,
                )
            )
        return tuple(bundles)

    @staticmethod
    def _quotient_adjacencies(
        scope: Scope, crossings: tuple[CrossingObject, ...]
    ) -> tuple[tuple[str, tuple[object, ...]], ...]:
        if scope.is_leaf:
            return ()
        child_index = {node: index for index, child in enumerate(scope.children) for node in child.members}
        grouped: dict[tuple[int, int], list[Edge]] = {}
        for crossing in crossings:
            for edge in crossing.usable_edges:
                left, right = child_index[edge.left], child_index[edge.right]
                grouped.setdefault((min(left, right), max(left, right)), []).append(edge)
        records: list[tuple[str, tuple[object, ...]]] = []
        for left in range(len(scope.children)):
            for right in range(left + 1, len(scope.children)):
                edges = grouped.get((left, right), [])
                records.append(
                    (
                        f"adjacency:{left}:{right}",
                        (len(edges), min((edge.cost for edge in edges), default=None)),
                    )
                )
        return tuple(records)


def _pair_distances(
    graph: Graph,
    nodes: tuple[Node, ...],
    category: Literal["boundary_distance", "landmark_distance"],
) -> tuple[SummaryDistance, ...]:
    records: list[SummaryDistance] = []
    for index, left in enumerate(nodes):
        for right in nodes[index + 1 :]:
            path = graph.shortest_path(left, right)
            records.append(
                SummaryDistance(
                    f"distance:{left}:{right}", left, right, path.cost if path is not None else None, category
                )
            )
    return tuple(records)


def _select_landmarks(boundary: tuple[Node, ...], count: int) -> tuple[Node, ...]:
    if count >= len(boundary):
        return boundary
    if count == 1:
        return boundary[:1]
    indexes = {round(index * (len(boundary) - 1) / (count - 1)) for index in range(count)}
    return tuple(boundary[index] for index in sorted(indexes))


def _parents(tree: ScopeTree) -> dict[str, Scope | None]:
    parents: dict[str, Scope | None] = {tree.root.identifier: None}

    def visit(scope: Scope) -> None:
        for child in scope.children:
            parents[child.identifier] = scope
            visit(child)

    visit(tree.root)
    return parents
