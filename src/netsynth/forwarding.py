"""Locator-based per-node FIB synthesis and distributed hop execution."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from heapq import heappop, heappush
from math import inf
from types import MappingProxyType

from netsynth.decomposition import Scope, ScopeTree
from netsynth.graph import Graph, Node
from netsynth.routing import PersistentObject, RoutingSnapshot
from netsynth.summaries import SummaryBuild


@dataclass(frozen=True, order=True)
class Locator:
    """Local child coordinates followed by a leaf-local selector."""

    components: tuple[int, ...]
    selector: int

    @property
    def component_count(self) -> int:
        """Count structural scalar components, including the selector."""
        return len(self.components) + 1


@dataclass(frozen=True)
class LocatorCatalog:
    """Construction-time mapping; never exposed to the data plane."""

    by_node: dict[Node, Locator]

    @classmethod
    def from_tree(cls, tree: ScopeTree) -> LocatorCatalog:
        """Derive deterministic scope-local coordinates and selectors."""
        by_node: dict[Node, Locator] = {}

        def visit(scope: Scope, prefix: tuple[int, ...]) -> None:
            if scope.is_leaf:
                for selector, node in enumerate(sorted(scope.members)):
                    by_node[node] = Locator(prefix, selector)
            else:
                for index, child in enumerate(scope.children):
                    visit(child, (*prefix, index))

        visit(tree.root, ())
        return cls(by_node)


@dataclass(frozen=True)
class ViewEdge:
    """Charged edge in an owner's personalized multiresolution view."""

    left: Locator
    right: Locator
    cost: float
    physical: bool


@dataclass(frozen=True)
class ForwardingKnowledge:
    """Immutable runtime knowledge; deliberately contains no Graph or ScopeTree."""

    owner: Locator
    neighbors: Mapping[Locator, float]
    fib: Mapping[tuple[int, ...] | Locator, Locator]
    local_members: frozenset[Locator]
    eligible: Mapping[tuple[int, ...] | Locator, tuple[Locator, ...]] | None = None

    def eligible_next_hops(self, destination: Locator) -> tuple[Locator, ...]:
        """Return progress-safe physical neighbors at the active resolution."""
        if self.eligible is None:
            return ()
        if destination.components == self.owner.components:
            return self.eligible.get(destination, ())
        common = _common_prefix(self.owner.components, destination.components)
        if common >= len(destination.components):
            return ()
        return self.eligible.get(destination.components[: common + 1], ())

    def next_hop(self, destination: Locator, hop_budget: int) -> Locator | None:
        """Look up one compiled physical neighbor; no route computation occurs here."""
        if hop_budget <= 0:
            return None
        if destination.components == self.owner.components:
            return self.fib.get(destination)
        common = _common_prefix(self.owner.components, destination.components)
        if common >= len(destination.components):
            return None
        prefix = destination.components[: common + 1]
        return self.fib.get(prefix)


@dataclass(frozen=True)
class ForwardingResult:
    """One executed distributed route or an explicit failure."""

    status: str
    locators: tuple[Locator, ...]
    cost: float
    hops: int


@dataclass(frozen=True)
class ForwardingNetwork:
    """Compiled per-node knowledge and charged state for one strategy/snapshot."""

    knowledge: Mapping[Locator, ForwardingKnowledge]
    state: RoutingSnapshot
    catalog: LocatorCatalog


@dataclass(frozen=True)
class PotentialCompilation:
    """Converged result plus auditable local fixed-point work."""

    network: ForwardingNetwork
    rounds: Mapping[str, int]


def compile_forwarding(build: SummaryBuild, catalog: LocatorCatalog) -> ForwardingNetwork:
    """Compile FIBs using only each owner's personalized declared view."""
    graph = build.graph
    tree = build.tree
    knowledge: dict[Locator, ForwardingKnowledge] = {}
    objects: dict[tuple[Node, str, str, str], PersistentObject] = {}
    for owner in sorted(graph.nodes):
        owner_locator = catalog.by_node[owner]
        leaf = tree.leaf_for(owner)
        local = graph.induced(leaf.members)
        local_locators = frozenset(catalog.by_node[node] for node in leaf.members)
        physical_neighbors = {catalog.by_node[neighbor]: edge.cost for neighbor, edge in graph.neighbors(owner)}
        view = _personalized_edges(build, catalog, owner, local)
        fib: dict[tuple[int, ...] | Locator, Locator] = {}
        for target in sorted(local.nodes):
            if target == owner:
                continue
            path = local.shortest_path(owner, target)
            if path is not None:
                fib[catalog.by_node[target]] = catalog.by_node[path.nodes[1]]
        for level, scope in enumerate(tree.lineage(owner)):
            if scope.is_leaf:
                continue
            own_index = owner_locator.components[level]
            active_prefix = owner_locator.components[:level]
            for child_index, _child in enumerate(scope.children):
                if child_index == own_index:
                    continue
                target_prefix = (*active_prefix, child_index)
                next_hop = _first_hop_to_prefix(owner_locator, target_prefix, active_prefix, view, physical_neighbors)
                if next_hop is not None:
                    fib[target_prefix] = next_hop
        knowledge[owner_locator] = ForwardingKnowledge(
            owner_locator,
            MappingProxyType(physical_neighbors),
            MappingProxyType(fib),
            local_locators,
        )
        _charge_owner(objects, build, catalog, owner, view, fib, local)
    return ForwardingNetwork(MappingProxyType(knowledge), RoutingSnapshot(objects), catalog)


def compile_scoped_potentials(graph: Graph, tree: ScopeTree, catalog: LocatorCatalog) -> PotentialCompilation:
    """Converge scoped potentials using only neighbor advertisements per update."""
    tables: dict[tuple[str, tuple[int, ...] | Locator], dict[Node, float]] = {}
    rounds: dict[str, int] = {}
    for scope in tree.scopes():
        if scope.is_leaf:
            for target in sorted(scope.members.intersection(graph.nodes)):
                key: tuple[int, ...] | Locator = catalog.by_node[target]
                values, count = _neighbor_fixed_point(graph, scope, frozenset((target,)))
                tables[(scope.identifier, key)] = values
                rounds[f"{scope.identifier}:{key}"] = count
            continue
        for child in scope.children:
            prefix = _scope_prefix(child, catalog)
            values, count = _neighbor_fixed_point(graph, scope, child.members.intersection(graph.nodes))
            tables[(scope.identifier, prefix)] = values
            rounds[f"{scope.identifier}:{prefix}"] = count

    knowledge: dict[Locator, ForwardingKnowledge] = {}
    objects: dict[tuple[Node, str, str, str], PersistentObject] = {}
    node_by_locator = {locator: node for node, locator in catalog.by_node.items()}
    for owner in sorted(graph.nodes):
        locator = catalog.by_node[owner]
        neighbors = {catalog.by_node[node]: edge.cost for node, edge in graph.neighbors(owner)}
        eligible: dict[tuple[int, ...] | Locator, tuple[Locator, ...]] = {}
        selected: dict[tuple[int, ...] | Locator, Locator] = {}
        lineage = tree.lineage(owner)
        for scope in lineage:
            keys: tuple[tuple[int, ...] | Locator, ...]
            if scope.is_leaf:
                keys = tuple(catalog.by_node[node] for node in sorted(scope.members.intersection(graph.nodes)))
            else:
                child_prefixes = tuple(_scope_prefix(child, catalog) for child in scope.children)
                keys = child_prefixes
            for key in keys:
                values = tables[(scope.identifier, key)]
                current = values.get(owner, inf)
                choices = tuple(
                    sorted(
                        catalog.by_node[neighbor]
                        for neighbor, _edge in graph.neighbors(owner)
                        if neighbor in scope.members and values.get(neighbor, inf) < current
                    )
                )
                eligible[key] = choices
                if choices:
                    selected[key] = min(
                        choices,
                        key=lambda hop: (
                            neighbors[hop] + values[node_by_locator[hop]],
                            hop,
                        ),
                    )
                key_size = key.component_count if isinstance(key, Locator) else len(key)
                objects[(owner, "potential_record", scope.identifier, str(key))] = PersistentObject(
                    (key, None if current == inf else current), key_size + 1
                )
                for hop in choices:
                    objects[(owner, "eligible_next_hop", scope.identifier, f"{key}:{hop}")] = PersistentObject(
                        (key, hop), key_size + hop.component_count
                    )
        fib = selected
        objects[(owner, "own_locator", "local", "self")] = PersistentObject((locator,), locator.component_count)
        for neighbor, cost in neighbors.items():
            objects[(owner, "neighbor_link", "local", str(neighbor))] = PersistentObject(
                (neighbor, cost), neighbor.component_count + 1
            )
        knowledge[locator] = ForwardingKnowledge(
            locator,
            MappingProxyType(neighbors),
            MappingProxyType(fib),
            frozenset(catalog.by_node[node] for node in tree.leaf_for(owner).members),
            MappingProxyType(eligible),
        )
    network = ForwardingNetwork(MappingProxyType(knowledge), RoutingSnapshot(objects), catalog)
    return PotentialCompilation(network, MappingProxyType(rounds))


def _neighbor_fixed_point(graph: Graph, scope: Scope, sinks: frozenset[Node]) -> tuple[dict[Node, float], int]:
    """Apply synchronous Bellman updates; each term reads only one neighbor advertisement."""
    present = graph.nodes.intersection(scope.members)
    values = {node: (0.0 if node in sinks else inf) for node in present}
    rounds = 0
    while True:
        updated = dict(values)
        for node in sorted(present.difference(sinks)):
            updated[node] = min(
                (edge.cost + values[neighbor] for neighbor, edge in graph.neighbors(node) if neighbor in present),
                default=inf,
            )
        if updated == values:
            return values, rounds
        values = updated
        rounds += 1


def _scope_prefix(scope: Scope, catalog: LocatorCatalog) -> tuple[int, ...]:
    """Return the Locator component prefix shared by a Scope's members."""
    components = [catalog.by_node[node].components for node in scope.members]
    length = min(len(value) for value in components)
    index = 0
    while index < length and len({value[index] for value in components}) == 1:
        index += 1
    return components[0][:index]


def _personalized_edges(
    build: SummaryBuild, catalog: LocatorCatalog, owner: Node, local: Graph
) -> tuple[ViewEdge, ...]:
    edges: list[ViewEdge] = [
        ViewEdge(catalog.by_node[edge.left], catalog.by_node[edge.right], edge.cost, True) for edge in local.edges
    ]
    for scope in build.tree.lineage(owner):
        if scope.is_leaf:
            continue
        view = build.views[scope.identifier]
        for crossing in view.crossings:
            edges.extend(
                ViewEdge(catalog.by_node[edge.left], catalog.by_node[edge.right], edge.cost, True)
                for edge in crossing.usable_edges
            )
        for child in scope.children:
            if owner in child.members:
                continue
            edges.extend(
                ViewEdge(catalog.by_node[edge.left], catalog.by_node[edge.right], edge.cost, False)
                for edge in build.views[child.identifier].summary.usable_edges()
            )
    return tuple(edges)


def _first_hop_to_prefix(
    owner: Locator,
    target_prefix: tuple[int, ...],
    active_prefix: tuple[int, ...],
    view: tuple[ViewEdge, ...],
    neighbors: Mapping[Locator, float],
) -> Locator | None:
    """Find a shortest abstract path ending at first target entry, with a physical first hop."""
    adjacency: dict[Locator, list[tuple[Locator, float]]] = {}
    for edge in view:
        if edge.left.components[: len(active_prefix)] != active_prefix:
            continue
        if edge.right.components[: len(active_prefix)] != active_prefix:
            continue
        left_target = edge.left.components[: len(target_prefix)] == target_prefix
        right_target = edge.right.components[: len(target_prefix)] == target_prefix
        if left_target and right_target:
            continue
        adjacency.setdefault(edge.left, []).append((edge.right, edge.cost))
        adjacency.setdefault(edge.right, []).append((edge.left, edge.cost))
    queue: list[tuple[float, tuple[Locator, ...], Locator]] = [(0.0, (owner,), owner)]
    best: dict[Locator, tuple[float, tuple[Locator, ...]]] = {owner: (0.0, (owner,))}
    while queue:
        cost, path, current = heappop(queue)
        if (cost, path) != best.get(current):
            continue
        if current.components[: len(target_prefix)] == target_prefix:
            first = path[1] if len(path) > 1 else None
            return first if first in neighbors else None
        for neighbor, edge_cost in adjacency.get(current, []):
            if current == owner and neighbor not in neighbors:
                continue
            candidate = (cost + edge_cost, (*path, neighbor))
            previous = best.get(neighbor)
            if previous is None or candidate < previous:
                best[neighbor] = candidate
                heappush(queue, (*candidate, neighbor))
    return None


def _charge_owner(
    objects: dict[tuple[Node, str, str, str], PersistentObject],
    build: SummaryBuild,
    catalog: LocatorCatalog,
    owner: Node,
    view: tuple[ViewEdge, ...],
    fib: dict[tuple[int, ...] | Locator, Locator],
    local: Graph,
) -> None:
    locator = catalog.by_node[owner]
    objects[(owner, "own_locator", "local", "self")] = PersistentObject((locator,), locator.component_count)
    for target, hop in fib.items():
        key_size = target.component_count if isinstance(target, Locator) else len(target)
        objects[(owner, "forwarding_entry", "fib", str(target))] = PersistentObject(
            (target, hop), key_size + hop.component_count
        )
    for node in sorted(build.tree.leaf_for(owner).members):
        objects[(owner, "local_topology_node", "local", str(catalog.by_node[node]))] = PersistentObject(
            (node in build.graph.nodes,), catalog.by_node[node].component_count
        )
    current_edges = {edge.key: edge for edge in local.edges}
    for edge in build.reference_graph.induced(build.tree.leaf_for(owner).members).edges:
        current = current_edges.get(edge.key)
        left, right = catalog.by_node[edge.left], catalog.by_node[edge.right]
        objects[(owner, "local_topology_link", "local", f"{left}:{right}")] = PersistentObject(
            (current.cost, current.capacity) if current is not None else (None, None),
            left.component_count + right.component_count + 2,
        )
    for view_edge in view:
        if not view_edge.physical:
            continue  # The published distance object already charges both locator references.
        if view_edge.left in {catalog.by_node[node] for node in local.nodes} and view_edge.right in {
            catalog.by_node[node] for node in local.nodes
        }:
            continue
        category = "crossing_locator_reference"
        key = (owner, category, "view", f"{view_edge.left}:{view_edge.right}")
        objects[key] = PersistentObject(
            (view_edge.cost,), view_edge.left.component_count + view_edge.right.component_count + 1
        )
    # Charge the Phase-2 logical summary objects actually consumed on this owner's lineage.
    for scope in build.tree.lineage(owner):
        if scope.is_leaf:
            continue
        view_scope = build.views[scope.identifier]
        for identifier, value in view_scope.quotient_adjacencies:
            objects[(owner, "quotient_adjacency", scope.identifier, identifier)] = PersistentObject(value, 3)
        for crossing in view_scope.crossings:
            representatives = crossing.value[2] if len(crossing.value) > 2 else ()
            metadata_scalars = 2 + len(representatives) if isinstance(representatives, tuple) else 2
            objects[(owner, crossing.category, scope.identifier, crossing.identifier)] = PersistentObject(
                crossing.value, metadata_scalars
            )
        for child in scope.children:
            if owner in child.members:
                continue
            summary = build.views[child.identifier].summary
            for portal in summary.portals:
                reference = catalog.by_node[portal]
                objects[(owner, "portal_record", child.identifier, str(reference))] = PersistentObject(
                    (reference,), reference.component_count
                )
            for record in summary.distances:
                left, right = catalog.by_node[record.left], catalog.by_node[record.right]
                objects[(owner, record.category, child.identifier, record.identifier)] = PersistentObject(
                    (left, right, record.cost), left.component_count + right.component_count + 1
                )
            if build.config.level == "r0":
                for node in summary.boundary_nodes:
                    reference = catalog.by_node[node]
                    objects[(owner, "reachability_boundary", child.identifier, str(reference))] = PersistentObject(
                        (reference,), reference.component_count
                    )
            for index, component in enumerate(summary.connectivity_components):
                component_id = f"component:{index}"
                objects[(owner, "reachability_component", child.identifier, component_id)] = PersistentObject(
                    (component_id,), 1
                )
                for node in component:
                    reference = catalog.by_node[node]
                    objects[(owner, "reachability_interface", child.identifier, f"{component_id}:{reference}")] = (
                        PersistentObject((component_id, reference), reference.component_count + 1)
                    )


def execute_forwarding(
    network: ForwardingNetwork,
    graph: Graph,
    source: Node,
    destination: Locator,
    hop_budget: int,
) -> ForwardingResult:
    """Execute local decisions; graph access here is validation and cost measurement only."""
    locator = network.catalog.by_node[source]
    reverse = {value: node for node, value in network.catalog.by_node.items()}
    visited = {locator}
    route = [locator]
    total = 0.0
    if locator == destination:
        return ForwardingResult("delivered", tuple(route), total, 0)
    for _hop in range(max(0, hop_budget)):
        knowledge = network.knowledge.get(locator)
        if knowledge is None:
            return ForwardingResult("no_route", tuple(route), total, len(route) - 1)
        next_locator = knowledge.next_hop(destination, hop_budget - len(route) + 1)
        if next_locator is None:
            return ForwardingResult("no_route", tuple(route), total, len(route) - 1)
        edge = graph.edge(reverse[locator], reverse[next_locator])
        if edge is None:
            return ForwardingResult("invalid_next_hop", (*route, next_locator), total, len(route))
        total += edge.cost
        route.append(next_locator)
        locator = next_locator
        if locator == destination:
            return ForwardingResult("delivered", tuple(route), total, len(route) - 1)
        if locator in visited:
            return ForwardingResult("loop", tuple(route), total, len(route) - 1)
        visited.add(locator)
    return ForwardingResult("hop_budget_exhausted", tuple(route), total, len(route) - 1)


def _common_prefix(left: tuple[int, ...], right: tuple[int, ...]) -> int:
    index = 0
    while index < min(len(left), len(right)) and left[index] == right[index]:
        index += 1
    return index
