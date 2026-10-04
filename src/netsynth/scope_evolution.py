"""Local layout generations and an explicit toy control-budget policy, not a partitioner."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise
from types import MappingProxyType
from typing import Literal

from netsynth.decomposition import Scope, ScopeTree
from netsynth.forwarding import Locator
from netsynth.graph import Graph, Node
from netsynth.scale4 import (
    AccessHandle,
    AccessRealization,
    AccessRegistry,
    AdvertisedPathlet,
    BoundaryTransitGraph,
    CrossingLink,
    DestinationAccessOffer,
    ExecutionResult,
    PathletHandle,
    PathletRegistry,
    PhysicalHop,
    RouteAction,
    RouteProgram,
    RouteQueryContext,
    ScopedTransitPathlet,
    ScopeRouteService,
    SourceAccessOffer,
    execute_route_program,
)


def physical_actions(graph: Graph) -> frozenset[PhysicalHop]:
    return frozenset(
        action
        for edge in graph.edges
        for action in (PhysicalHop(edge.left, edge.right), PhysicalHop(edge.right, edge.left))
    )


def local_realization(graph: Graph, source: Node, target: Node) -> tuple[PhysicalHop, ...]:
    """Only a leaf owner calls this on its own induced graph, never a remote planner."""
    path = graph.shortest_path(source, target)
    if path is None:
        raise ValueError("local owner has no physical realization")
    return tuple(PhysicalHop(left, right) for left, right in pairwise(path.nodes))


def local_cost(graph: Graph, actions: tuple[PhysicalHop, ...]) -> float:
    cost = 0.0
    for action in actions:
        edge = graph.edge(action.left, action.right)
        if edge is None:
            raise ValueError("owner-local realization contains a nonphysical link")
        cost += edge.cost
    return cost


@dataclass(frozen=True)
class LayoutRoute:
    program: RouteProgram
    access: MappingProxyType[str, AccessRegistry]
    context: RouteQueryContext


class _Leaf:
    def __init__(self, scope_id: str, graph: Graph, boundaries: frozenset[Node]) -> None:
        self.scope_id, self.graph, self.boundaries = scope_id, graph, boundaries
        self.registry = PathletRegistry(scope_id, physical_actions(graph))
        slot = 0
        for source in sorted(boundaries):
            for target in sorted(boundaries - {source}):
                actions = local_realization(graph, source, target)
                metric = local_cost(graph, actions)
                self.registry.publish(
                    ScopedTransitPathlet(
                        AdvertisedPathlet(PathletHandle(scope_id, slot, 0), source, target, metric), actions
                    )
                )
                slot += 1
        self.btg = self.registry.export(boundaries)

    @property
    def local_records(self) -> int:
        return len(self.graph.nodes) + len(self.graph.edges) + self.registry.persistent_records

    def offers(
        self,
        node: Node,
        query: str,
        destination: Locator | None = None,
    ) -> tuple[tuple[SourceAccessOffer, ...], tuple[DestinationAccessOffer, ...], AccessRegistry]:
        access = AccessRegistry(
            self.scope_id,
            query,
            self.boundaries,
            physical_actions(self.graph),
            destination=destination,
            destination_node=node if destination is not None else None,
        )
        source_offers: list[SourceAccessOffer] = []
        target_offers: list[DestinationAccessOffer] = []
        for token, boundary in enumerate(sorted(self.boundaries)):
            source, target = (node, boundary) if destination is None else (boundary, node)
            actions = local_realization(self.graph, source, target)
            cost = local_cost(self.graph, actions)
            handle = AccessHandle(self.scope_id, query, token)
            realization = AccessRealization(source, target, actions)
            if destination is None:
                offer = SourceAccessOffer(boundary, cost, handle)
                access.publish_source(offer, realization)
                source_offers.append(offer)
            else:
                target_offer = DestinationAccessOffer(boundary, cost, handle)
                access.publish_destination(target_offer, realization)
                target_offers.append(target_offer)
        return tuple(source_offers), tuple(target_offers), access


class LayoutGeneration:
    """One connected, laminar layout; all knowledge is inside a declared owning region."""

    def __init__(
        self,
        scope_id: str,
        prefix: tuple[int, ...],
        generation: int,
        local_graph: Graph,
        partition: tuple[frozenset[Node], ...],
        boundaries: frozenset[Node],
    ) -> None:
        if not prefix or any(component < 0 for component in prefix) or generation < 0:
            raise ValueError("layout needs a stable Scope prefix and non-negative local generation")
        if (
            not partition
            or any(not members for members in partition)
            or not boundaries
            or not boundaries <= local_graph.nodes
        ):
            raise ValueError("layout requires nonempty partition and owner-local boundaries")
        if not local_graph.is_connected():
            raise ValueError("Routing Scope must be connected")
        self.scope_id, self.prefix, self.generation = scope_id, prefix, generation
        self.members, self.boundaries = local_graph.nodes, boundaries
        self.flat = len(partition) == 1
        ids = tuple(f"{scope_id}/layout-{generation}/child-{label}" for label in range(len(partition)))
        self.tree = ScopeTree(
            Scope(
                scope_id,
                local_graph.nodes,
                tuple(Scope(owner, members) for owner, members in zip(ids, partition, strict=True)),
            )
        )
        self.tree.validate(local_graph)
        owner_by_node = {node: label for label, members in enumerate(partition) for node in members}
        crossings = tuple(
            CrossingLink(edge.left, edge.right, edge.cost)
            for edge in local_graph.edges
            if owner_by_node[edge.left] != owner_by_node[edge.right]
        )
        ports = boundaries | frozenset(node for crossing in crossings for node in (crossing.left, crossing.right))
        # This belongs to the scoped construction/ownership controller, not the Route Service.
        self._owner_by_node = owner_by_node
        self._leaves = tuple(
            _Leaf(owner, local_graph.induced(members), ports & members)
            for owner, members in zip(ids, partition, strict=True)
        )
        self.child_btgs = tuple(leaf.btg for leaf in self._leaves)
        self.crossings = crossings
        self.service = ScopeRouteService(
            scope_id, ids, {node: ids[owner_by_node[node]] for node in ports}, self.child_btgs, crossings
        )
        self.phase: Literal["prepared", "active", "retired"] = "prepared"
        self._queries: list[dict[str, AccessRegistry]] = []
        self._query_sequence = 0

    def locator(self, node: Node) -> Locator:
        label = self._owner_by_node[node]
        selector = sorted(self._leaves[label].graph.nodes).index(node)
        return Locator((*self.prefix, self.generation, label), selector)

    def _destination(self, locator: Locator) -> tuple[_Leaf, Node]:
        if locator.components[:-1] != (*self.prefix, self.generation):
            raise ValueError("Locator belongs to a different Scope/layout generation")
        label = locator.components[-1]
        if not 0 <= label < len(self._leaves):
            raise ValueError("unknown generation-local child label")
        leaf = self._leaves[label]
        nodes = sorted(leaf.graph.nodes)
        if not 0 <= locator.selector < len(nodes):
            raise ValueError("unknown owner-local attachment selector")
        return leaf, nodes[locator.selector]

    def compile(self, source: Node, destination: Locator) -> LayoutRoute:
        if self.phase != "active":
            raise ValueError("layout is not active")
        target_leaf, target = self._destination(destination)
        source_leaf = self._leaves[self._owner_by_node[source]]
        self._query_sequence += 1
        query = f"{self.scope_id}@{self.generation}/q{self._query_sequence}"
        source_offers, _, source_access = source_leaf.offers(source, query)
        # Source and destination owners may coincide, but Access tokens must not alias.
        if source_leaf is target_leaf:
            access = AccessRegistry(
                source_leaf.scope_id,
                query,
                source_leaf.boundaries,
                physical_actions(source_leaf.graph),
                destination=destination,
                destination_node=target,
            )
            for offer in source_offers:
                realization = source_access.lookup(offer.handle)
                assert realization is not None
                access.publish_source(offer, realization)
            targets: list[DestinationAccessOffer] = []
            for token, boundary in enumerate(sorted(target_leaf.boundaries), start=len(source_offers)):
                actions = local_realization(target_leaf.graph, boundary, target)
                cost = local_cost(target_leaf.graph, actions)
                target_offer = DestinationAccessOffer(boundary, cost, AccessHandle(target_leaf.scope_id, query, token))
                access.publish_destination(target_offer, AccessRealization(boundary, target, actions))
                targets.append(target_offer)
            target_offers = tuple(targets)
            access_map = {source_leaf.scope_id: access}
        else:
            _, target_offers, target_access = target_leaf.offers(target, query, destination)
            access_map = {source_leaf.scope_id: source_access, target_leaf.scope_id: target_access}
        compiled = self.service.compile(query, destination, source_offers, target_offers)
        if compiled is None:
            raise ValueError("layout summary has no route")
        self._queries.append(access_map)  # Owner-local query lifetime; clear on retirement.
        return LayoutRoute(compiled.program, MappingProxyType(access_map), RouteQueryContext(query, source))

    def realize_parent_contract(self, contract: AdvertisedPathlet) -> tuple[RouteAction, ...]:
        """Resolve using only crossings and immediate-child BTGs, never child interiors."""
        source_owner = self._leaves[self._owner_by_node[contract.ingress]].scope_id
        target_owner = self._leaves[self._owner_by_node[contract.egress]].scope_id
        query = f"{self.scope_id}@{self.generation}/contract-{contract.handle.slot}"
        source = SourceAccessOffer(contract.ingress, 0, AccessHandle(source_owner, query, 0))
        target = DestinationAccessOffer(contract.egress, 0, AccessHandle(target_owner, query, 1))
        compiled = self.service.compile(query, self.locator(contract.egress), (source,), (target,))
        if compiled is None:
            raise ValueError("new layout cannot realize exported hard contract")
        return compiled.program.actions[1:-1]  # Strip the empty query-time boundary offers.

    def retire(self) -> None:
        self.phase = "retired"
        for access in self._queries:
            access.clear()  # Even cached frozen-executor views lose old owner-local Access state.
        self._queries.clear()
        for leaf in self._leaves:
            for pathlet in leaf.btg.pathlets:
                leaf.registry.retire(pathlet.handle)


def hard_contracts(btg: BoundaryTransitGraph) -> frozenset[tuple[PathletHandle, Node, Node]]:
    return frozenset((item.handle, item.ingress, item.egress) for item in btg.pathlets)


def hard_update_count(before: BoundaryTransitGraph, after: BoundaryTransitGraph) -> int:
    """Count hard advertisements/interface add/withdraw; exclude soft metrics."""
    if before.scope_id != after.scope_id:
        raise ValueError("hard-change comparison must name the same exporting Scope")
    return len(before.boundaries ^ after.boundaries) + len(hard_contracts(before) ^ hard_contracts(after))


class RoutingScope:
    """Stable owner, at most two live layouts, a Scope-local monotonic generation floor."""

    def __init__(
        self, scope_id: str, prefix: tuple[int, ...], members: frozenset[Node], boundaries: frozenset[Node]
    ) -> None:
        self.scope_id, self.prefix, self.members, self.boundaries = scope_id, prefix, members, boundaries
        self.layouts: dict[int, LayoutGeneration] = {}
        self._generation_floor = -1
        self.preferred_generation: int | None = None
        self.parent_registry: PathletRegistry | None = None
        self._contracts: tuple[AdvertisedPathlet, ...] = tuple(
            AdvertisedPathlet(PathletHandle(scope_id, slot, 0), left, right, 1.0)
            for slot, (left, right) in enumerate(
                (left, right) for left in sorted(boundaries) for right in sorted(boundaries - {left})
            )
        )
        self.parent_hard_updates = 0

    def prepare(self, generation: int, local_graph: Graph, partition: tuple[frozenset[Node], ...]) -> LayoutGeneration:
        if local_graph.nodes != self.members:
            raise ValueError("formation must receive exactly the owning Scope's local region, not global topology")
        if generation <= self._generation_floor or len(self.layouts) >= 2:
            raise ValueError("generation must be fresh and only two layouts may coexist")
        layout = LayoutGeneration(self.scope_id, self.prefix, generation, local_graph, partition, self.boundaries)
        self.layouts[generation] = layout
        self._generation_floor = generation
        return layout

    def activate(self, generation: int) -> None:
        layout = self.layouts[generation]
        if layout.phase != "prepared":
            raise ValueError("activate only a prepared layout")
        # A validated owner-view rebind for the SAME live external hard contracts, not
        # handle retirement/republication. No new external slot/generation is allocated.
        if self.parent_registry is not None and any(
            self.parent_registry.lookup(item.handle) is None for item in self._contracts
        ):
            raise ValueError("cannot revive a withdrawn external hard contract")
        registry = PathletRegistry(
            self.scope_id,
            frozenset(
                action
                for crossing in layout.crossings
                for action in (PhysicalHop(crossing.left, crossing.right), PhysicalHop(crossing.right, crossing.left))
            ),
            layout.child_btgs,
        )
        for contract in self._contracts:
            registry.publish(ScopedTransitPathlet(contract, layout.realize_parent_contract(contract)))
        before = self.export() if self.parent_registry is not None else None
        self.parent_registry = registry
        layout.phase = "active"
        self.preferred_generation = generation
        if before is not None:
            self.parent_hard_updates += hard_update_count(before, self.export())

    def export(self) -> BoundaryTransitGraph:
        if self.parent_registry is None:
            raise ValueError("Scope has no active external contracts")
        return self.parent_registry.export(self.boundaries)

    def registries(self) -> MappingProxyType[str, PathletRegistry]:
        registries = {
            leaf.scope_id: leaf.registry
            for layout in self.layouts.values()
            if layout.phase == "active"
            for leaf in layout._leaves
        }
        if self.parent_registry is not None:
            registries[self.scope_id] = self.parent_registry
        return MappingProxyType(registries)

    def retire(self, generation: int) -> None:
        if generation == self.preferred_generation or self.layouts[generation].phase != "active":
            raise ValueError("retire only a non-preferred active layout after replacement activation")
        self.layouts[generation].retire()
        del self.layouts[generation]

    def discard(self, generation: int) -> None:
        if self.layouts[generation].phase != "prepared":
            raise ValueError("discard only a prepared candidate")
        self.layouts[generation].retire()
        del self.layouts[generation]

    def execute(
        self, physical_graph: Graph, route: LayoutRoute, hop_budget: int
    ) -> ExecutionResult | Literal["stale_layout"]:
        parts = route.program.destination.components
        if parts[:-2] != self.prefix or len(parts) != len(self.prefix) + 2:
            return "stale_layout"
        layout = self.layouts.get(parts[-2])
        if layout is None or layout.phase != "active":
            return "stale_layout"
        return execute_route_program(
            physical_graph, self.registries(), route.access, route.program, route.context, hop_budget
        )


@dataclass(frozen=True)
class ControlBudget:
    root_local_records: int
    local_total_records: int
    maximum_controller_records: int
    child_boundary_records: int
    child_btg_pathlet_records: int
    parent_boundary_records: int
    parent_btg_pathlet_records: int
    exported_hard_updates: int

    @property
    def parent_visible_records(self) -> int:
        return self.parent_boundary_records + self.parent_btg_pathlet_records


def control_budget(layout: LayoutGeneration, exported: BoundaryTransitGraph, hard_updates: int = 0) -> ControlBudget:
    """Count real owner/control objects, not hidden whole-graph distance oracles."""
    if hard_updates < 0 or exported.scope_id != layout.scope_id:
        raise ValueError("budget needs non-negative hard updates and the correct owner export")
    registry = PathletRegistry(
        layout.scope_id,
        frozenset(
            action
            for crossing in layout.crossings
            for action in (PhysicalHop(crossing.left, crossing.right), PhysicalHop(crossing.right, crossing.left))
        ),
        layout.child_btgs,
    )
    for contract in exported.pathlets:
        registry.publish(ScopedTransitPathlet(contract, layout.realize_parent_contract(contract)))
    metadata = 1 + len(layout.members) + len(layout._leaves)  # Layout, ownership associations, child identities.
    local = metadata + layout.service.persistent_records + registry.persistent_records
    if layout.flat:
        # The single leaf and its service view are colocated. Charge the actual model
        # objects rather than pretending their stored one-child view is free.
        local += layout._leaves[0].local_records
        local_costs = [local]
    else:
        local_costs = [local, *(leaf.local_records for leaf in layout._leaves)]
    child_boundaries = sum(len(btg.boundaries) for btg in layout.child_btgs)
    child_pathlets = sum(len(btg.pathlets) for btg in layout.child_btgs)
    return ControlBudget(
        local,
        sum(local_costs),
        max(local_costs),
        child_boundaries,
        child_pathlets,
        len(exported.boundaries),
        len(exported.pathlets),
        hard_updates,
    )


@dataclass(frozen=True)
class MigrationCost:
    rebuilt_records: int
    renumbered_attachments: int
    binding_publications: int
    overlap_records: int
    exported_hard_updates: int

    @property
    def total(self) -> int:
        return (
            self.rebuilt_records
            + self.renumbered_attachments
            + self.binding_publications
            + self.overlap_records
            + self.exported_hard_updates
        )


def migration_cost(
    old: LayoutGeneration,
    new: LayoutGeneration,
    old_budget: ControlBudget,
    new_budget: ControlBudget,
    affected_endpoints: int,
) -> MigrationCost:
    if old.scope_id != new.scope_id or old.members != new.members or affected_endpoints < 0:
        raise ValueError("migration must be inside one stable Scope with non-negative Endpoint count")
    return MigrationCost(
        new_budget.local_total_records,
        sum(old.locator(node) != new.locator(node) for node in old.members),
        2 * affected_endpoints,
        old_budget.local_total_records + new_budget.local_total_records,
        new_budget.exported_hard_updates,
    )


@dataclass(frozen=True)
class FormationPolicy:
    """Fixture-only units/weights: controller pressure + parent records + hard updates."""

    horizon: int = 20
    persistent_samples: int = 3
    minimum_gain: int = 5
    safety_margin: int = 20
    parent_weight: int = 1
    hard_update_weight: int = 4
    total_state_weight: int = 1

    def __post_init__(self) -> None:
        if (
            min(self.horizon, self.persistent_samples, self.minimum_gain) < 1
            or min(self.safety_margin, self.parent_weight, self.hard_update_weight, self.total_state_weight) < 0
        ):
            raise ValueError("formation policy needs positive horizon/gain/persistence and non-negative weights")

    def score(self, budget: ControlBudget) -> int:
        return (
            budget.maximum_controller_records
            + self.total_state_weight * budget.local_total_records
            + self.parent_weight * budget.parent_visible_records
            + self.hard_update_weight * budget.exported_hard_updates
        )

    def evaluate(
        self, old: ControlBudget, new: ControlBudget, migration: MigrationCost, observed_gains: tuple[int, ...]
    ) -> str:
        gain = self.score(old) - self.score(new)
        if gain < self.minimum_gain:
            return (
                "keep_flat"
                if new.maximum_controller_records >= old.maximum_controller_records
                else "insufficient_benefit"
            )
        if (
            len(observed_gains) < self.persistent_samples
            or min(observed_gains[-self.persistent_samples :]) < self.minimum_gain
        ):
            return "hysteresis"
        if (
            self.horizon * min(gain, *observed_gains[-self.persistent_samples :])
            <= migration.total + self.safety_margin
        ):
            return "migration_cost"
        return "accept"
