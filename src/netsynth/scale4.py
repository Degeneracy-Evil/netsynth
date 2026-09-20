"""Minimal semantic prototype for Scale-4 scoped route programs.

This module deliberately models contracts and information ownership, not a
general routing framework or a pathlet-selection algorithm.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from heapq import heappop, heappush
from itertools import count, pairwise
from math import inf
from types import MappingProxyType
from typing import Literal

from netsynth.decomposition import Scope
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

    def __init__(self, scope: Scope) -> None:
        self.scope_id = scope.identifier
        self._members = scope.members
        self._descendant_scope_ids = frozenset(_descendant_ids(scope))
        self._active: dict[PathletHandle, ScopedTransitPathlet] = {}
        self._retired: set[PathletHandle] = set()

    def publish(self, pathlet: ScopedTransitPathlet) -> None:
        """Install one generation without replacing or reviving another one."""
        handle = pathlet.advertisement.handle
        if handle.owner_scope != self.scope_id:
            raise ValueError("registry can publish only locally owned pathlets")
        if pathlet.advertisement.ingress not in self._members or pathlet.advertisement.egress not in self._members:
            raise ValueError("pathlet boundaries must belong to the owner Scope")
        if handle in self._active or handle in self._retired:
            raise ValueError("a pathlet generation cannot be reused")
        self._validate_realization(pathlet.realization)
        self._active[handle] = pathlet

    def lookup(self, handle: PathletHandle) -> ScopedTransitPathlet | None:
        """Resolve only the exact active generation; never alias by slot."""
        return self._active.get(handle)

    def repair(self, handle: PathletHandle, realization: tuple[RouteAction, ...]) -> None:
        """Replace hidden realization while preserving the hard generation."""
        current = self._active.get(handle)
        if current is None:
            raise KeyError(handle)
        self._validate_realization(realization)
        self._active[handle] = replace(current, realization=realization)

    def update_soft_metric(self, handle: PathletHandle, metric: float) -> None:
        """Update route quality without changing the hard contract generation."""
        if metric <= 0:
            raise ValueError("a pathlet metric must be positive")
        current = self._active.get(handle)
        if current is None:
            raise KeyError(handle)
        advertisement = replace(current.advertisement, soft_metric=metric)
        self._active[handle] = replace(current, advertisement=advertisement)

    def retire(self, handle: PathletHandle) -> None:
        """Make an exact generation fail closed for all subsequent packets."""
        if handle not in self._active:
            raise KeyError(handle)
        del self._active[handle]
        self._retired.add(handle)

    def export(self, boundaries: frozenset[Node]) -> BoundaryTransitGraph:
        """Create an opaque BTG containing no realization actions."""
        if not boundaries.issubset(self._members):
            raise ValueError("exported boundaries must belong to the owner Scope")
        advertisements = tuple(
            sorted((pathlet.advertisement for pathlet in self._active.values()), key=lambda item: item.handle)
        )
        return BoundaryTransitGraph(self.scope_id, boundaries, advertisements)

    def _validate_realization(self, realization: tuple[RouteAction, ...]) -> None:
        for action in realization:
            if isinstance(action, PhysicalHop) and (
                action.left not in self._members or action.right not in self._members
            ):
                raise ValueError("pathlet physical hops must remain inside the owner Scope")
            if isinstance(action, PathletHandle) and action.owner_scope not in self._descendant_scope_ids:
                raise ValueError("pathlets may delegate only into proper descendant Scopes")
            if isinstance(action, AccessHandle):
                raise ValueError("persistent pathlets cannot depend on query-time access state")

    @property
    def persistent_records(self) -> int:
        """Charge hard metadata, realizations, and retained anti-alias tombstones."""
        return 1 + sum(1 + len(pathlet.realization) for pathlet in self._active.values()) + len(self._retired)


def _descendant_ids(scope: Scope) -> tuple[str, ...]:
    return tuple(child.identifier for child in scope.children) + tuple(
        identifier for child in scope.children for identifier in _descendant_ids(child)
    )


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


@dataclass(frozen=True)
class DestinationAccessOffer:
    """Query-time opaque route from one boundary to the destination position."""

    boundary: Node
    cost: float
    handle: AccessHandle


@dataclass(frozen=True)
class AccessRealization:
    """Ingress-local query state hidden from the parent Route Service."""

    start: Node
    end: Node
    actions: tuple[RouteAction, ...]


@dataclass(frozen=True)
class RouteQueryContext:
    """Ephemeral access state retained only by the requesting edge/control service."""

    query_id: str
    source: Node
    destination: Node
    realizations: MappingProxyType[AccessHandle, AccessRealization]

    def __post_init__(self) -> None:
        if any(handle.query_id != self.query_id for handle in self.realizations):
            raise ValueError("access realization belongs to a different query")
        if any(
            isinstance(action, AccessHandle)
            for realization in self.realizations.values()
            for action in realization.actions
        ):
            raise ValueError("query-time access realizations must be flattened before execution")

    @property
    def charged_records(self) -> int:
        """Charge each access object and each action in its opaque realization."""
        return 1 + sum(1 + len(realization.actions) for realization in self.realizations.values())


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
        scope: Scope,
        child_btgs: tuple[BoundaryTransitGraph, ...],
        crossings: tuple[CrossingLink, ...],
    ) -> None:
        child_ids = [btg.scope_id for btg in child_btgs]
        if len(child_ids) != len(set(child_ids)):
            raise ValueError("a Route Service may store one BTG per immediate child")
        expected_ids = {child.identifier for child in scope.children}
        if set(child_ids) != expected_ids:
            raise ValueError("Route Service BTGs must correspond exactly to immediate child Scopes")
        child_by_node = {node: child.identifier for child in scope.children for node in child.members}
        if (
            len(child_by_node) != sum(len(child.members) for child in scope.children)
            or frozenset(child_by_node) != scope.members
        ):
            raise ValueError("immediate child Scopes must be a disjoint exact partition")
        scope_by_id = {child.identifier: child for child in scope.children}
        for btg in child_btgs:
            if not btg.boundaries.issubset(scope_by_id[btg.scope_id].members):
                raise ValueError("child BTG boundaries must belong to that immediate child Scope")
        for crossing in crossings:
            left_child = child_by_node.get(crossing.left)
            right_child = child_by_node.get(crossing.right)
            if left_child is None or right_child is None or left_child == right_child:
                raise ValueError("crossing link must join two immediate child Scopes")
        self.scope_id = scope.identifier
        self.immediate_child_ids = tuple(child.identifier for child in scope.children)
        self.child_btgs = child_btgs
        self.crossings = crossings

    @property
    def persistent_records(self) -> int:
        """Charge exactly the pushed summaries and locally owned crossings."""
        hierarchy_records = 1 + len(self.immediate_child_ids)
        return hierarchy_records + sum(btg.persistent_records for btg in self.child_btgs) + len(self.crossings)

    def compile(
        self,
        destination: Locator,
        source_offers: tuple[SourceAccessOffer, ...],
        destination_offers: tuple[DestinationAccessOffer, ...],
    ) -> CompilationResult | None:
        """Resolve one route using only immediate-child summaries and query offers."""
        query_ids = {offer.handle.query_id for offer in source_offers} | {
            offer.handle.query_id for offer in destination_offers
        }
        if len(query_ids) > 1:
            raise ValueError("all access offers in one pull must belong to the same query")
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
            if source_offer.cost < 0:
                raise ValueError("access cost cannot be negative")
            add_arc(source_key, source_offer.boundary, source_offer.cost, source_offer.handle)
        for destination_offer in destination_offers:
            if destination_offer.cost < 0:
                raise ValueError("access cost cannot be negative")
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
        access = context.realizations.get(action)
        if access is None:
            return result("missing_access_state")
        if current != access.start:
            return result("contract_violation")
        stack.append(_CompletionFrame(access.end, frame.depth))
        stack.extend(_ActionFrame(nested, frame.depth) for nested in reversed(access.actions))

    if current != context.destination:
        return result("contract_violation")
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
