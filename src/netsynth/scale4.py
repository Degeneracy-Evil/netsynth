"""Minimal semantic prototype for Scale-4 scoped route programs.

This module deliberately models contracts and information ownership, not a
general routing framework or a pathlet-selection algorithm.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from heapq import heappop, heappush
from itertools import count, pairwise
from math import inf
from types import MappingProxyType
from typing import Literal

from netsynth.forwarding import Locator
from netsynth.graph import Graph, Node


@dataclass(frozen=True, order=True)
class PathletHandle:
    """A Scope-local forwarding slot plus an immutable contract generation."""

    owner_scope: str
    slot: int
    generation: int

    def __post_init__(self) -> None:
        if self.slot < 0 or self.generation < 0:
            raise ValueError("pathlet slot and generation must be non-negative")


@dataclass(frozen=True, order=True)
class AccessHandle:
    """Opaque query-local handle; it is never part of a persistent BTG."""

    owner_scope: str
    query_id: str
    token: int

    def __post_init__(self) -> None:
        if self.token < 0:
            raise ValueError("access token must be non-negative")


@dataclass(frozen=True)
class PhysicalHop:
    """One directed use of an undirected physical link."""

    left: Node
    right: Node


type RouteAction = PhysicalHop | PathletHandle | AccessHandle


@dataclass(frozen=True)
class AdvertisedPathlet:
    """The complete parent-visible hard contract plus its soft metric."""

    handle: PathletHandle
    ingress: Node
    egress: Node
    soft_metric: float

    def __post_init__(self) -> None:
        if self.ingress == self.egress:
            raise ValueError("a transit pathlet must join distinct boundaries")
        if self.soft_metric <= 0:
            raise ValueError("a pathlet metric must be positive")


@dataclass(frozen=True)
class ScopedTransitPathlet:
    """Owner-local pathlet state; realization is never exported to the parent."""

    advertisement: AdvertisedPathlet
    realization: tuple[RouteAction, ...]


@dataclass(frozen=True)
class BoundaryTransitGraph:
    """Persistent child-to-parent summary over real boundary interfaces only."""

    scope_id: str
    boundaries: frozenset[Node]
    pathlets: tuple[AdvertisedPathlet, ...]

    def __post_init__(self) -> None:
        handles: set[PathletHandle] = set()
        for pathlet in self.pathlets:
            if pathlet.handle.owner_scope != self.scope_id:
                raise ValueError("BTG may advertise only pathlets owned by its Scope")
            if pathlet.ingress not in self.boundaries or pathlet.egress not in self.boundaries:
                raise ValueError("BTG pathlet endpoints must be real boundary interfaces")
            if pathlet.handle in handles:
                raise ValueError("BTG cannot advertise a pathlet handle twice")
            handles.add(pathlet.handle)

    @property
    def persistent_records(self) -> int:
        """Charge boundary vertices and advertised pathlet records."""
        return len(self.boundaries) + len(self.pathlets)


class PathletRegistry:
    """Scope-owned hard contracts and hidden forwarding realizations."""

    def __init__(
        self,
        scope_id: str,
        physical_actions: frozenset[PhysicalHop],
        child_btgs: tuple[BoundaryTransitGraph, ...] = (),
    ) -> None:
        child_ids = [btg.scope_id for btg in child_btgs]
        if len(child_ids) != len(set(child_ids)):
            raise ValueError("pathlet registry may receive one BTG per immediate child")
        if scope_id in child_ids:
            raise ValueError("a Scope cannot consume its own BTG as an immediate-child contract")
        self.scope_id = scope_id
        self._physical_actions = physical_actions
        self._immediate_child_contracts = {pathlet.handle: pathlet for btg in child_btgs for pathlet in btg.pathlets}
        self._active_by_slot: dict[int, ScopedTransitPathlet] = {}
        self._generation_high_water: dict[int, int] = {}

    def publish(self, pathlet: ScopedTransitPathlet) -> None:
        """Install one generation without replacing or reviving another one."""
        handle = pathlet.advertisement.handle
        if handle.owner_scope != self.scope_id:
            raise ValueError("registry can publish only locally owned pathlets")
        if handle.slot in self._active_by_slot:
            raise ValueError("a pathlet slot already has an active generation")
        previous = self._generation_high_water.get(handle.slot)
        if previous is not None and handle.generation <= previous:
            raise ValueError("pathlet generation must increase monotonically per slot")
        self._validate_pathlet(pathlet)
        self._active_by_slot[handle.slot] = pathlet
        self._generation_high_water[handle.slot] = handle.generation

    def lookup(self, handle: PathletHandle) -> ScopedTransitPathlet | None:
        """Resolve only the exact active generation; never alias by slot."""
        pathlet = self._active_by_slot.get(handle.slot)
        return pathlet if pathlet is not None and pathlet.advertisement.handle == handle else None

    def repair(self, handle: PathletHandle, realization: tuple[RouteAction, ...]) -> None:
        """Replace hidden realization while preserving the hard generation."""
        current = self.lookup(handle)
        if current is None:
            raise KeyError(handle)
        repaired = replace(current, realization=realization)
        self._validate_pathlet(repaired)
        self._active_by_slot[handle.slot] = repaired

    def update_soft_metric(self, handle: PathletHandle, metric: float) -> None:
        """Update route quality without changing the hard contract generation."""
        if metric <= 0:
            raise ValueError("a pathlet metric must be positive")
        current = self.lookup(handle)
        if current is None:
            raise KeyError(handle)
        advertisement = replace(current.advertisement, soft_metric=metric)
        self._active_by_slot[handle.slot] = replace(current, advertisement=advertisement)

    def retire(self, handle: PathletHandle) -> None:
        """Make an exact generation fail closed for all subsequent packets."""
        if self.lookup(handle) is None:
            raise KeyError(handle)
        del self._active_by_slot[handle.slot]

    def export(self, boundaries: frozenset[Node]) -> BoundaryTransitGraph:
        """Create an opaque BTG containing no realization actions."""
        advertisements = tuple(
            sorted((pathlet.advertisement for pathlet in self._active_by_slot.values()), key=lambda item: item.handle)
        )
        if any(
            advertisement.ingress not in boundaries or advertisement.egress not in boundaries
            for advertisement in advertisements
        ):
            raise ValueError("exported pathlet endpoints must be declared owner boundaries")
        return BoundaryTransitGraph(self.scope_id, boundaries, advertisements)

    def _validate_pathlet(self, pathlet: ScopedTransitPathlet) -> None:
        advertised = pathlet.advertisement
        _validate_action_sequence(
            advertised.ingress,
            advertised.egress,
            pathlet.realization,
            self._physical_actions,
            self._immediate_child_contracts,
        )

    @property
    def persistent_records(self) -> int:
        """Charge active realizations plus one generation watermark per used slot."""
        return (
            1
            + len(self._generation_high_water)
            + sum(1 + len(pathlet.realization) for pathlet in self._active_by_slot.values())
        )

    @property
    def generation_record_count(self) -> int:
        """Expose bounded semantic history for validation/accounting."""
        return len(self._generation_high_water)


def _validate_action_sequence(
    start: Node,
    end: Node,
    actions: tuple[RouteAction, ...],
    physical_actions: frozenset[PhysicalHop],
    child_contracts: dict[PathletHandle, AdvertisedPathlet],
) -> None:
    current = start
    for action in actions:
        if isinstance(action, PhysicalHop):
            if action not in physical_actions:
                raise ValueError("physical action is not visible at the owner Scope level")
            action_start, action_end = action.left, action.right
        elif isinstance(action, PathletHandle):
            contract = child_contracts.get(action)
            if contract is None:
                raise ValueError("pathlet action is not exported by an immediate child")
            action_start, action_end = contract.ingress, contract.egress
        else:
            raise ValueError("persistent owner-local realizations cannot contain AccessHandles")
        if action_start != current:
            raise ValueError("realization actions must be continuous from the advertised ingress")
        current = action_end
    if current != end:
        raise ValueError("realization must end at the advertised egress")


@dataclass(frozen=True)
class CrossingLink:
    """One parent-owned physical link between immediate child Scopes."""

    left: Node
    right: Node
    cost: float

    def __post_init__(self) -> None:
        if self.left == self.right or self.cost <= 0:
            raise ValueError("crossing links need distinct endpoints and positive cost")


@dataclass(frozen=True)
class SourceAccessOffer:
    """Query-time opaque route from the source position to one boundary."""

    boundary: Node
    cost: float
    handle: AccessHandle

    def __post_init__(self) -> None:
        if self.cost < 0:
            raise ValueError("access cost cannot be negative")


@dataclass(frozen=True)
class DestinationAccessOffer:
    """Query-time opaque route from one boundary to the destination position."""

    boundary: Node
    cost: float
    handle: AccessHandle

    def __post_init__(self) -> None:
        if self.cost < 0:
            raise ValueError("access cost cannot be negative")


@dataclass(frozen=True)
class AccessRealization:
    """Owner-local ephemeral realization hidden from parent and ingress."""

    start: Node
    end: Node
    actions: tuple[RouteAction, ...]


class AccessRegistry:
    """One Scope's opaque, ephemeral realization state for one route query."""

    def __init__(
        self,
        scope_id: str,
        query_id: str,
        boundaries: frozenset[Node],
        physical_actions: frozenset[PhysicalHop],
        child_btgs: tuple[BoundaryTransitGraph, ...] = (),
    ) -> None:
        child_ids = [btg.scope_id for btg in child_btgs]
        if len(child_ids) != len(set(child_ids)) or scope_id in child_ids:
            raise ValueError("Access registry child BTGs must name distinct immediate children")
        self.scope_id = scope_id
        self.query_id = query_id
        self.boundaries = boundaries
        self._physical_actions = physical_actions
        self._immediate_child_contracts = {pathlet.handle: pathlet for btg in child_btgs for pathlet in btg.pathlets}
        self._realizations: dict[AccessHandle, AccessRealization] = {}

    def publish_source(self, offer: SourceAccessOffer, realization: AccessRealization) -> None:
        """Validate and retain an opaque source-to-boundary offer locally."""
        self._validate_offer(offer.handle, offer.boundary)
        if realization.end != offer.boundary:
            raise ValueError("source Access Offer must end at its advertised boundary")
        self._publish(offer.handle, realization)

    def publish_destination(self, offer: DestinationAccessOffer, realization: AccessRealization) -> None:
        """Validate and retain an opaque boundary-to-destination offer locally."""
        self._validate_offer(offer.handle, offer.boundary)
        if realization.start != offer.boundary:
            raise ValueError("destination Access Offer must start at its advertised boundary")
        self._publish(offer.handle, realization)

    def _validate_offer(self, handle: AccessHandle, boundary: Node) -> None:
        if handle.owner_scope != self.scope_id:
            raise ValueError("Access Offer owner does not match its owner-local registry")
        if handle.query_id != self.query_id:
            raise ValueError("Access Offer query does not match its owner-local registry")
        if boundary not in self.boundaries:
            raise ValueError("Access Offer endpoint is not an owner boundary")

    def _publish(self, handle: AccessHandle, realization: AccessRealization) -> None:
        if handle in self._realizations:
            raise ValueError("Access Handle cannot be reused within one query")
        _validate_action_sequence(
            realization.start,
            realization.end,
            realization.actions,
            self._physical_actions,
            self._immediate_child_contracts,
        )
        self._realizations[handle] = realization

    def lookup(self, handle: AccessHandle) -> AccessRealization | None:
        """Resolve an exact handle only inside its owning query-local registry."""
        if handle.owner_scope != self.scope_id or handle.query_id != self.query_id:
            return None
        return self._realizations.get(handle)

    @property
    def charged_records(self) -> int:
        """Charge the ephemeral registry, access objects, and their actions."""
        return 1 + sum(1 + len(realization.actions) for realization in self._realizations.values())


@dataclass(frozen=True)
class RouteQueryContext:
    """Ingress-visible query identity and source, with no Access realizations."""

    query_id: str
    source: Node

    @property
    def charged_records(self) -> int:
        """Charge the ingress-local query identity/source record."""
        return 1


@dataclass(frozen=True)
class RouteProgram:
    """A destination Locator plus a sequential list of coarse route actions."""

    destination: Locator
    actions: tuple[RouteAction, ...]

    @property
    def sequential_header_length(self) -> int:
        """Count top-level packet-carried actions, independently of recursion."""
        return len(self.actions)

    @property
    def dependencies(self) -> frozenset[PathletHandle]:
        """Return hard pathlet generations directly referenced by the program."""
        return frozenset(action for action in self.actions if isinstance(action, PathletHandle))


@dataclass(frozen=True)
class CompilationResult:
    """One pull-route answer with explicit transient-state accounting."""

    program: RouteProgram
    query_records: int
    transient_vertices: int


@dataclass(frozen=True)
class _Arc:
    target: Node | str
    cost: float
    action: RouteAction


class ScopeRouteService:
    """Route resolver whose persistent view stops at immediate-child contracts."""

    def __init__(
        self,
        scope_id: str,
        immediate_child_ids: tuple[str, ...],
        boundary_owner: Mapping[Node, str],
        child_btgs: tuple[BoundaryTransitGraph, ...],
        crossings: tuple[CrossingLink, ...],
    ) -> None:
        child_ids = [btg.scope_id for btg in child_btgs]
        if len(child_ids) != len(set(child_ids)) or len(immediate_child_ids) != len(set(immediate_child_ids)):
            raise ValueError("a Route Service may store one BTG per immediate child")
        if set(child_ids) != set(immediate_child_ids):
            raise ValueError("Route Service BTGs must correspond exactly to immediate child Scopes")
        declared_boundaries = frozenset(boundary for btg in child_btgs for boundary in btg.boundaries)
        if frozenset(boundary_owner) != declared_boundaries:
            raise ValueError("boundary ownership must cover exactly the immediate-child BTG vertices")
        for btg in child_btgs:
            if any(boundary_owner[boundary] != btg.scope_id for boundary in btg.boundaries):
                raise ValueError("BTG boundary ownership must name the exporting immediate child")
        for crossing in crossings:
            left_child = boundary_owner.get(crossing.left)
            right_child = boundary_owner.get(crossing.right)
            if left_child is None or right_child is None or left_child == right_child:
                raise ValueError("crossing link must join owned boundaries of two immediate child Scopes")
        self.scope_id = scope_id
        self.immediate_child_ids = immediate_child_ids
        self.boundary_owner = MappingProxyType(dict(boundary_owner))
        self.child_btgs = child_btgs
        self.crossings = crossings

    @property
    def persistent_records(self) -> int:
        """Charge exactly the pushed summaries and locally owned crossings."""
        hierarchy_records = 1 + len(self.immediate_child_ids)
        return hierarchy_records + sum(btg.persistent_records for btg in self.child_btgs) + len(self.crossings)

    def compile(
        self,
        query_id: str,
        destination: Locator,
        source_offers: tuple[SourceAccessOffer, ...],
        destination_offers: tuple[DestinationAccessOffer, ...],
    ) -> CompilationResult | None:
        """Resolve one route using only immediate-child summaries and query offers."""

        def validate_offer(offer: SourceAccessOffer | DestinationAccessOffer) -> None:
            if offer.handle.query_id != query_id:
                raise ValueError("Access Offer query identity does not match the route query")
            if offer.handle.owner_scope not in self.immediate_child_ids:
                raise ValueError("Access Offer owner is not an immediate child")
            if self.boundary_owner.get(offer.boundary) != offer.handle.owner_scope:
                raise ValueError("Access Offer boundary is not owned by its declared Scope")

        for source_offer in source_offers:
            validate_offer(source_offer)
        for destination_offer in destination_offers:
            validate_offer(destination_offer)
        handles = [offer.handle for offer in source_offers] + [offer.handle for offer in destination_offers]
        if len(handles) != len(set(handles)):
            raise ValueError("an Access Handle may describe only one offer in a route query")
        source_key = "__query_source__"
        destination_key = "__query_destination__"
        adjacency: dict[Node | str, list[_Arc]] = {source_key: [], destination_key: []}

        def add_arc(left: Node | str, right: Node | str, cost: float, action: RouteAction) -> None:
            adjacency.setdefault(left, []).append(_Arc(right, cost, action))
            adjacency.setdefault(right, [])

        for btg in self.child_btgs:
            for boundary in btg.boundaries:
                adjacency.setdefault(boundary, [])
            for pathlet in btg.pathlets:
                add_arc(pathlet.ingress, pathlet.egress, pathlet.soft_metric, pathlet.handle)
        for crossing in self.crossings:
            add_arc(crossing.left, crossing.right, crossing.cost, PhysicalHop(crossing.left, crossing.right))
            add_arc(crossing.right, crossing.left, crossing.cost, PhysicalHop(crossing.right, crossing.left))
        for source_offer in source_offers:
            add_arc(source_key, source_offer.boundary, source_offer.cost, source_offer.handle)
        for destination_offer in destination_offers:
            add_arc(
                destination_offer.boundary,
                destination_key,
                destination_offer.cost,
                destination_offer.handle,
            )

        route = _shortest_abstract_route(adjacency, source_key, destination_key)
        if route is None:
            return None
        query_records = len(source_offers) + len(destination_offers) + len(route)
        return CompilationResult(RouteProgram(destination, route), query_records, len(adjacency))


def _shortest_abstract_route(
    adjacency: dict[Node | str, list[_Arc]], source: Node | str, destination: Node | str
) -> tuple[RouteAction, ...] | None:
    distances: dict[Node | str, float] = {source: 0.0}
    actions: dict[Node | str, tuple[RouteAction, ...]] = {source: ()}
    serial = count()
    queue: list[tuple[float, int, Node | str]] = [(0.0, next(serial), source)]
    while queue:
        distance, _order, current = heappop(queue)
        if distance != distances.get(current):
            continue
        if current == destination:
            return actions[current]
        for arc in sorted(adjacency[current], key=lambda item: (item.cost, repr(item.target), repr(item.action))):
            candidate = distance + arc.cost
            if candidate < distances.get(arc.target, inf):
                distances[arc.target] = candidate
                actions[arc.target] = (*actions[current], arc.action)
                heappush(queue, (candidate, next(serial), arc.target))
    return None


type ExecutionStatus = Literal[
    "delivered",
    "hop_budget_exhausted",
    "invalid_physical_hop",
    "stale_pathlet",
    "missing_access_state",
    "contract_violation",
]


@dataclass(frozen=True)
class ExecutionResult:
    """Physical execution outcome and separately measured header dimensions."""

    status: ExecutionStatus
    path: tuple[Node, ...]
    cost: float
    physical_hops: int
    sequential_header_length: int
    maximum_stack_depth: int


@dataclass(frozen=True)
class _ActionFrame:
    action: RouteAction
    depth: int


@dataclass(frozen=True)
class _CompletionFrame:
    expected: Node
    depth: int
    handle: PathletHandle | None = None


type _Frame = _ActionFrame | _CompletionFrame


def execute_route_program(
    graph: Graph,
    registries: MappingProxyType[str, PathletRegistry],
    access_registries: MappingProxyType[str, AccessRegistry],
    program: RouteProgram,
    context: RouteQueryContext,
    hop_budget: int,
) -> ExecutionResult:
    """Execute labels hop-by-hop; the physical graph is only a data-plane validator."""
    if hop_budget < 0:
        raise ValueError("hop budget cannot be negative")
    current = context.source
    path = [current]
    cost = 0.0
    hops = 0
    maximum_depth = 0
    active_handles: set[PathletHandle] = set()
    stack: list[_Frame] = [_ActionFrame(action, 0) for action in reversed(program.actions)]

    def result(status: ExecutionStatus) -> ExecutionResult:
        return ExecutionResult(
            status,
            tuple(path),
            cost,
            hops,
            program.sequential_header_length,
            maximum_depth,
        )

    while stack:
        frame = stack.pop()
        if isinstance(frame, _CompletionFrame):
            if current != frame.expected:
                return result("contract_violation")
            if frame.handle is not None:
                active_handles.remove(frame.handle)
            continue
        action = frame.action
        if isinstance(action, PhysicalHop):
            if hops >= hop_budget:
                return result("hop_budget_exhausted")
            edge = graph.edge(action.left, action.right)
            if current != action.left or edge is None:
                return result("invalid_physical_hop")
            current = action.right
            path.append(current)
            cost += edge.cost
            hops += 1
            continue
        if isinstance(action, PathletHandle):
            if action in active_handles:
                return result("contract_violation")
            registry = registries.get(action.owner_scope)
            pathlet = None if registry is None else registry.lookup(action)
            if pathlet is None:
                return result("stale_pathlet")
            advertised = pathlet.advertisement
            if current != advertised.ingress:
                return result("contract_violation")
            nested_depth = frame.depth + 1
            maximum_depth = max(maximum_depth, nested_depth)
            active_handles.add(action)
            stack.append(_CompletionFrame(advertised.egress, nested_depth, action))
            stack.extend(_ActionFrame(nested, nested_depth) for nested in reversed(pathlet.realization))
            continue
        if action.query_id != context.query_id:
            return result("missing_access_state")
        access_registry = access_registries.get(action.owner_scope)
        access = None if access_registry is None else access_registry.lookup(action)
        if access is None:
            return result("missing_access_state")
        if current != access.start:
            return result("contract_violation")
        stack.append(_CompletionFrame(access.end, frame.depth))
        stack.extend(_ActionFrame(nested, frame.depth) for nested in reversed(access.actions))

    return result("delivered")


def execute_flat_local(
    graph: Graph, source: Node, destination: Node, locator: Locator, hop_budget: int
) -> ExecutionResult:
    """Show graceful Scale-0/1/2/3 degeneration with no Scale-4 route state."""
    if hop_budget < 0:
        raise ValueError("hop budget cannot be negative")
    del locator  # The local selector is the target in a real local forwarding table.
    path = graph.shortest_path(source, destination)
    if path is None:
        return ExecutionResult("contract_violation", (source,), 0.0, 0, 0, 0)
    required_hops = len(path.nodes) - 1
    if required_hops > hop_budget:
        prefix = path.nodes[: hop_budget + 1]
        prefix_cost = 0.0
        for left, right in pairwise(prefix):
            edge = graph.edge(left, right)
            if edge is None:
                raise AssertionError("shortest path contains a non-physical hop")
            prefix_cost += edge.cost
        return ExecutionResult("hop_budget_exhausted", prefix, prefix_cost, hop_budget, 0, 0)
    return ExecutionResult("delivered", path.nodes, path.cost, required_hops, 0, 0)


def reachability_floor_holds(graph: Graph, scope_members: frozenset[Node], summary: BoundaryTransitGraph) -> bool:
    """Child-side validation that BTG reachability matches internal boundary reachability."""
    internal = graph.induced(scope_members)
    adjacency: dict[Node, set[Node]] = {boundary: set() for boundary in summary.boundaries}
    for pathlet in summary.pathlets:
        adjacency[pathlet.ingress].add(pathlet.egress)

    def advertised_reachable(source: Node, destination: Node) -> bool:
        pending = [source]
        seen = {source}
        while pending:
            current = pending.pop()
            for neighbor in adjacency[current]:
                if neighbor == destination:
                    return True
                if neighbor not in seen:
                    seen.add(neighbor)
                    pending.append(neighbor)
        return source == destination

    for source in summary.boundaries:
        for destination in summary.boundaries:
            physical = internal.shortest_path(source, destination) is not None
            if physical != advertised_reachable(source, destination):
                return False
    return True
