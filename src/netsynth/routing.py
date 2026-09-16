"""Flat and information-budgeted recursive routing models."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise
from math import inf
from typing import Protocol

from netsynth.decomposition import Scope
from netsynth.graph import Edge, Graph, Node, Path
from netsynth.summaries import PublishedSummary, SummaryBuild

StateKey = tuple[Node, str, str, str]


@dataclass(frozen=True)
class PersistentObject:
    """One charged architecture object and its normalized scalar footprint."""

    value: tuple[object, ...]
    normalized_size: int


@dataclass(frozen=True)
class RoutingSnapshot:
    """All persistent forwarding and control state consumed by a strategy."""

    objects: dict[StateKey, PersistentObject]


class RoutingStrategy(Protocol):
    """Common route and persistent-state interface."""

    @property
    def name(self) -> str:
        """Return the strategy name recorded in results."""
        ...

    def route(self, source: Node, target: Node) -> Path | None:
        """Compute a physical route from declared information."""
        ...

    def snapshot(self) -> RoutingSnapshot:
        """Materialize every persistent object consumed by the model."""
        ...


class FlatRouting:
    """Full-topology shortest-path baseline with fully charged global knowledge."""

    name = "flat_full_knowledge"

    def __init__(self, graph: Graph, reference_graph: Graph | None = None) -> None:
        self._graph = graph
        self._reference = graph if reference_graph is None else reference_graph

    def route(self, source: Node, target: Node) -> Path | None:
        """Return a physical shortest path."""
        return self._graph.shortest_path(source, target)

    def snapshot(self) -> RoutingSnapshot:
        """Charge forwarding entries plus replicated full topology at every node."""
        objects: dict[StateKey, PersistentObject] = {}
        current_edges = {edge.key: edge for edge in self._graph.edges}
        for owner in sorted(self._graph.nodes):
            for target in sorted(self._reference.nodes):
                if owner == target:
                    continue
                path = self.route(owner, target)
                _add(
                    objects,
                    owner,
                    "forwarding_entry",
                    "global",
                    str(target),
                    (path.nodes[1] if path is not None else None, path.cost if path is not None else None),
                    3,
                )
            for node in sorted(self._reference.nodes):
                _add(objects, owner, "global_topology_node", "global", str(node), (node in self._graph.nodes,), 1)
            for edge in self._reference.edges:
                current = current_edges.get(edge.key)
                _add(
                    objects,
                    owner,
                    "global_topology_link",
                    "global",
                    f"{edge.left}:{edge.right}",
                    (current.cost, current.capacity) if current is not None else (None, None),
                    4,
                )
        return RoutingSnapshot(objects)


class CompressedRouting:
    """Recursive routing that consumes exactly one composable summary build."""

    def __init__(self, build: SummaryBuild) -> None:
        self._build = build
        self._route_cache: dict[tuple[str, Node, Node], Path | None] = {}

    @property
    def name(self) -> str:
        """Return the configured semantic summary level."""
        return self._build.config.name

    def route(self, source: Node, target: Node) -> Path | None:
        """Route using local leaf detail, published child summaries, and declared crossings."""
        if source not in self._build.graph.nodes or target not in self._build.graph.nodes:
            return None
        return self._route_in_scope(self._build.tree.root, source, target)

    def _route_in_scope(self, scope: Scope, source: Node, target: Node) -> Path | None:
        key = (scope.identifier, source, target)
        if key not in self._route_cache:
            self._route_cache[key] = self._compute_route_in_scope(scope, source, target)
        return self._route_cache[key]

    def _compute_route_in_scope(self, scope: Scope, source: Node, target: Node) -> Path | None:
        if source == target:
            return Path((source,), 0.0)
        if scope.is_leaf:
            return self._build.graph.shortest_path(source, target, scope.members)
        source_child = next(child for child in scope.children if source in child.members)
        target_child = next(child for child in scope.children if target in child.members)
        if self._build.config.level == "s0":
            if source_child == target_child:
                return self._route_in_scope(source_child, source, target)
            return self._route_s0(scope, source, target)
        return self._route_overlay(scope, source, target)

    def _route_s0(self, scope: Scope, source: Node, target: Node) -> Path | None:
        view = self._build.views[scope.identifier]
        child_index = {node: index for index, child in enumerate(scope.children) for node in child.members}
        edges_by_pair: dict[tuple[int, int], list[Edge]] = {}
        for crossing_object in view.crossings:
            for edge in crossing_object.usable_edges:
                left, right = child_index[edge.left], child_index[edge.right]
                edges_by_pair.setdefault((min(left, right), max(left, right)), []).append(edge)
        quotient = Graph(
            set(range(len(scope.children))),
            [Edge(left, right, min(edge.cost for edge in edges)) for (left, right), edges in edges_by_pair.items()],
        )
        source_index, target_index = child_index[source], child_index[target]
        coarse = quotient.shortest_path(source_index, target_index)
        if coarse is None:
            return None
        result = [source]
        current = source
        for left_index, right_index in zip(coarse.nodes, coarse.nodes[1:], strict=False):
            candidates = edges_by_pair[(min(left_index, right_index), max(left_index, right_index))]
            selected_edge = min(candidates, key=lambda edge: (edge.cost, edge.left, edge.right))
            left_scope = scope.children[left_index]
            if selected_edge.left in left_scope.members:
                exit_node, entry_node = selected_edge.left, selected_edge.right
            else:
                exit_node, entry_node = selected_edge.right, selected_edge.left
            internal = self._route_in_scope(left_scope, current, exit_node)
            if internal is None:
                return None
            result.extend(internal.nodes[1:])
            result.append(entry_node)
            current = entry_node
        final = self._route_in_scope(scope.children[target_index], current, target)
        if final is None:
            return None
        result.extend(final.nodes[1:])
        return _physical_path(self._build.graph, result)

    def _route_overlay(self, scope: Scope, source: Node, target: Node) -> Path | None:
        view = self._build.views[scope.identifier]
        edges = [edge for child in scope.children for edge in self._summary(child).usable_edges()]
        edges.extend(edge for crossing in view.crossings for edge in crossing.usable_edges)
        interface_nodes = {node for edge in edges for node in (edge.left, edge.right)}
        source_child = next(child for child in scope.children if source in child.members)
        target_child = next(child for child in scope.children if target in child.members)
        if source_child == target_child:
            direct = self._route_in_scope(source_child, source, target)
            if direct is not None:
                edges.append(Edge(source, target, direct.cost))
        for interface in sorted(interface_nodes.intersection(source_child.members)):
            path = self._route_in_scope(source_child, source, interface)
            if path is not None and source != interface:
                edges.append(Edge(source, interface, path.cost))
        for interface in sorted(interface_nodes.intersection(target_child.members)):
            path = self._route_in_scope(target_child, interface, target)
            if path is not None and interface != target:
                edges.append(Edge(interface, target, path.cost))
        overlay = Graph(set(self._build.graph.nodes.intersection(scope.members)), edges)
        abstract = overlay.shortest_path(source, target)
        if abstract is None:
            return None
        result = [source]
        for left, right in zip(abstract.nodes, abstract.nodes[1:], strict=False):
            left_child = next(child for child in scope.children if left in child.members)
            right_child = next(child for child in scope.children if right in child.members)
            if left_child != right_child:
                physical_edge = self._build.graph.edge(left, right)
                if physical_edge is None:
                    return None
                segment: Path | None = Path((left, right), physical_edge.cost)
            else:
                segment = self._route_in_scope(left_child, left, right)
            if segment is None:
                return None
            result.extend(segment.nodes[1:])
        return _physical_path(self._build.graph, result)

    def _summary(self, scope: Scope) -> PublishedSummary:
        return self._build.views[scope.identifier].summary

    def snapshot(self) -> RoutingSnapshot:
        """Charge forwarding, local detail, and every replicated consumed summary object."""
        objects: dict[StateKey, PersistentObject] = {}
        graph = self._build.graph
        reference = self._build.reference_graph
        current_edges = {edge.key: edge for edge in graph.edges}
        for owner in sorted(graph.nodes):
            leaf = self._build.tree.leaf_for(owner)
            for node in sorted(leaf.members):
                _add(
                    objects,
                    owner,
                    "local_topology_node",
                    leaf.identifier,
                    str(node),
                    (node in graph.nodes,),
                    1,
                )
            for edge in reference.induced(leaf.members).edges:
                current = current_edges.get(edge.key)
                _add(
                    objects,
                    owner,
                    "local_topology_link",
                    leaf.identifier,
                    f"{edge.left}:{edge.right}",
                    (current.cost, current.capacity) if current is not None else (None, None),
                    4,
                )
            self._add_forwarding(objects, owner)
            for scope in self._build.tree.lineage(owner):
                if scope.is_leaf:
                    continue
                view = self._build.views[scope.identifier]
                for identifier, value in view.quotient_adjacencies:
                    _add(objects, owner, "quotient_adjacency", scope.identifier, identifier, value, 3)
                for crossing in view.crossings:
                    _add(
                        objects,
                        owner,
                        crossing.category,
                        scope.identifier,
                        crossing.identifier,
                        crossing.value,
                        crossing.normalized_size,
                    )
                for child in scope.children:
                    self._add_summary(objects, owner, self._summary(child))
        return RoutingSnapshot(objects)

    def _add_forwarding(self, objects: dict[StateKey, PersistentObject], owner: Node) -> None:
        leaf = self._build.tree.leaf_for(owner)
        for target in sorted(leaf.members):
            if target != owner:
                self._add_forwarding_entry(objects, owner, "local", str(target), target)
        for scope in self._build.tree.lineage(owner):
            if scope.is_leaf:
                continue
            own_child = next(child for child in scope.children if owner in child.members)
            for child in scope.children:
                if child != own_child:
                    candidates = sorted(child.members.intersection(self._build.graph.nodes))
                    aggregate_target: Node | None = candidates[0] if candidates else None
                    self._add_forwarding_entry(
                        objects, owner, f"aggregate:{scope.identifier}", child.identifier, aggregate_target
                    )

    def _add_forwarding_entry(
        self,
        objects: dict[StateKey, PersistentObject],
        owner: Node,
        scope_id: str,
        identifier: str,
        target: Node | None,
    ) -> None:
        path = self.route(owner, target) if target is not None else None
        value = (path.nodes[1] if path is not None else None, path.cost if path is not None else None)
        _add(objects, owner, "forwarding_entry", scope_id, identifier, value, 3)

    def _add_summary(self, objects: dict[StateKey, PersistentObject], owner: Node, summary: PublishedSummary) -> None:
        for portal in summary.portals:
            _add(
                objects,
                owner,
                "portal_record",
                summary.scope_id,
                str(portal),
                (portal in self._build.graph.nodes,),
                1,
            )
        for record in summary.distances:
            _add(
                objects,
                owner,
                record.category,
                summary.scope_id,
                record.identifier,
                (record.left, record.right, record.cost),
                3,
            )


def validate_path(graph: Graph, path: Path, source: Node, target: Node) -> bool:
    """Check endpoints, physical adjacency, simplicity, and reported cost."""
    if not path.nodes or path.nodes[0] != source or path.nodes[-1] != target:
        return False
    if len(set(path.nodes)) != len(path.nodes):
        return False
    physical = _physical_path(graph, list(path.nodes))
    return physical is not None and abs(physical.cost - path.cost) < max(1.0, abs(physical.cost)) * 1e-12


def _physical_path(graph: Graph, nodes: list[Node]) -> Path | None:
    if len(set(nodes)) != len(nodes):
        return None
    cost = 0.0
    for left, right in pairwise(nodes):
        edge = graph.edge(left, right)
        if edge is None:
            return None
        cost += edge.cost
    return Path(tuple(nodes), cost) if cost < inf else None


def _add(
    objects: dict[StateKey, PersistentObject],
    owner: Node,
    category: str,
    scope_id: str,
    identifier: str,
    value: tuple[object, ...],
    normalized_size: int,
) -> None:
    objects[(owner, category, scope_id, identifier)] = PersistentObject(value, normalized_size)
