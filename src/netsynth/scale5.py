"""Scale-5 identity, binding-cache, and final-delivery semantic model."""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from secrets import token_bytes
from types import MappingProxyType
from typing import Literal

from netsynth.forwarding import Locator
from netsynth.graph import Graph, Node
from netsynth.scale4 import (
    AccessRegistry,
    ExecutionResult,
    PathletRegistry,
    RouteProgram,
    RouteQueryContext,
    execute_route_program,
)


@dataclass(frozen=True, order=True)
class EndpointID:
    """Opaque bytes with no topology or authority-placement semantics."""

    value: bytes

    def __post_init__(self) -> None:
        if not self.value:
            raise ValueError("Endpoint ID cannot be empty")

    @classmethod
    def generate(cls) -> EndpointID:
        """Generate locally; 32 bytes is a prototype choice, not a wire requirement."""
        return cls(token_bytes(32))


@dataclass(frozen=True)
class EndpointBinding:
    """A complete Locator set, ordered by a version local to this EID."""

    eid: EndpointID
    version: int
    locators: frozenset[Locator]
    cache_lifetime: int

    def __post_init__(self) -> None:
        if self.version < 1 or self.cache_lifetime < 0:
            raise ValueError("binding version must be positive and lifetime non-negative")


class BindingService:
    """Tiny fixed-shard authority; each shard models one logical replica group."""

    def __init__(self, authority_locators: tuple[Locator, ...]) -> None:
        if not authority_locators or len(set(authority_locators)) != len(authority_locators):
            raise ValueError("authority groups need distinct infrastructure Locators")
        self.authority_locators = authority_locators
        self._shards: tuple[dict[EndpointID, EndpointBinding], ...] = tuple({} for _ in authority_locators)
        self.read_count = 0
        self.last_read_locator: Locator | None = None

    def authority_index(self, eid: EndpointID) -> int:
        """Toy deterministic hashing of the flat key, independent of attachment."""
        return int.from_bytes(sha256(eid.value).digest()) % len(self._shards)

    def publish(self, eid: EndpointID, locators: frozenset[Locator], cache_lifetime: int = 10) -> EndpointBinding:
        """Atomically replace one complete record in its logical authority group."""
        shard = self._shards[self.authority_index(eid)]
        previous = shard.get(eid)
        binding = EndpointBinding(eid, 1 if previous is None else previous.version + 1, locators, cache_lifetime)
        shard[eid] = binding
        return binding

    def read(self, eid: EndpointID, authority_locator: Locator) -> EndpointBinding | None:
        """Read authoritative state; None means unknown, not an empty Locator set."""
        index = self.authority_index(eid)
        if authority_locator != self.authority_locators[index]:
            raise ValueError("binding read was addressed to the wrong authoritative Locator")
        self.read_count += 1
        self.last_read_locator = authority_locator
        return self._shards[index].get(eid)

    @property
    def record_count(self) -> int:
        """Count stored bindings without implying real replication cost."""
        return sum(len(shard) for shard in self._shards)


@dataclass(frozen=True)
class _CacheEntry:
    binding: EndpointBinding
    expires_at: int


class BindingResolver:
    """Demand cache using a local logical clock and Locator-addressed authority."""

    def __init__(self, locator: Locator, service: BindingService) -> None:
        self.locator = locator
        self._service = service
        self._clock = 0
        self._cache: dict[EndpointID, _CacheEntry] = {}

    def advance(self, ticks: int) -> None:
        """Advance only this resolver's cache clock; no global clock is needed."""
        if ticks < 0:
            raise ValueError("local time cannot move backwards")
        self._clock += ticks

    def accept(self, binding: EndpointBinding) -> bool:
        """Apply a received response only if it cannot regress this EID's state."""
        previous = self._cache.get(binding.eid)
        if previous is not None:
            if binding.version < previous.binding.version:
                return False
            if binding.version == previous.binding.version:
                if binding != previous.binding:
                    raise ValueError("one BindingVersion cannot identify conflicting records")
                return False  # A delayed duplicate must not extend its original cache lifetime.
        self._cache[binding.eid] = _CacheEntry(binding, self._clock + binding.cache_lifetime)
        return True

    def resolve(self, eid: EndpointID) -> EndpointBinding | None:
        """Use a still-valid cache entry even when the authority has changed."""
        cached = self._cache.get(eid)
        if cached is not None and self._clock < cached.expires_at:
            return cached.binding
        return self.resolve_fresh(eid)

    def resolve_fresh(self, eid: EndpointID, known_version: int = 0) -> EndpointBinding | None:
        """Read authority directly; never silently return a regressing response."""
        authority_locator = self._service.authority_locators[self._service.authority_index(eid)]
        binding = self._service.read(eid, authority_locator)
        previous = self._cache.get(eid)
        minimum_version = max(known_version, 0 if previous is None else previous.binding.version)
        if binding is None:
            if minimum_version:
                raise ValueError("authoritative read lost a previously observed binding")
            return None
        if binding.version < minimum_version:
            raise ValueError("fresh authoritative response is older than known binding state")
        self.accept(binding)
        # Explicit revalidation may refresh a lifetime; a delayed duplicate via accept() cannot.
        self._cache[eid] = _CacheEntry(binding, self._clock + binding.cache_lifetime)
        return binding

    @property
    def cache_record_count(self) -> int:
        """Count demand entries, including expired records retained as version floors."""
        return len(self._cache)


@dataclass(frozen=True)
class Endpoint:
    """Mock logical Endpoint; the inbox is only evidence of final delivery."""

    eid: EndpointID
    inbox: list[bytes] = field(default_factory=list)


class LocalAttachment:
    """Delivery table at one fixed forwarding position; only local EIDs occur here."""

    def __init__(self, locator: Locator, node: Node) -> None:
        self.locator = locator
        self.node = node
        self._endpoints: dict[EndpointID, Endpoint] = {}

    def attach(self, endpoint: Endpoint) -> None:
        """Install a local EID without changing any routing object."""
        existing = self._endpoints.get(endpoint.eid)
        if existing is not None and existing is not endpoint:
            raise ValueError("local EID already denotes a different Endpoint")
        self._endpoints[endpoint.eid] = endpoint

    def detach(self, eid: EndpointID) -> None:
        """Remove local presence; create no forwarding pointer."""
        del self._endpoints[eid]

    def deliver(self, eid: EndpointID, payload: bytes) -> Literal["delivered", "eid_absent"]:
        """Fail closed if the exact EID is absent, even if another Endpoint is present."""
        endpoint = self._endpoints.get(eid)
        if endpoint is None:
            return "eid_absent"
        endpoint.inbox.append(payload)
        return "delivered"

    @property
    def record_count(self) -> int:
        """Count local Endpoint records, not the global namespace."""
        return len(self._endpoints)


@dataclass(frozen=True)
class EndpointPacket:
    """Scale-5 envelope; only the nested Route Program enters Scale-4 forwarding."""

    destination_eid: EndpointID
    selected_locator: Locator
    program: RouteProgram
    payload: bytes

    def __post_init__(self) -> None:
        if self.selected_locator != self.program.destination:
            raise ValueError("selected Locator must match the compiled Route Program")


@dataclass(frozen=True)
class EndpointDeliveryResult:
    """Keep routing failure separate from explicit final EID rejection."""

    status: Literal["delivered", "routing_failure", "wrong_attachment", "eid_absent"]
    routing: ExecutionResult


def deliver_endpoint_packet(
    graph: Graph,
    registries: MappingProxyType[str, PathletRegistry],
    access_registries: MappingProxyType[str, AccessRegistry],
    context: RouteQueryContext,
    hop_budget: int,
    packet: EndpointPacket,
    attachment: LocalAttachment,
) -> EndpointDeliveryResult:
    """Route by Locator, then deliver by exact EID only at the reached attachment."""
    routing = execute_route_program(graph, registries, access_registries, packet.program, context, hop_budget)
    if routing.status != "delivered":
        return EndpointDeliveryResult("routing_failure", routing)
    if routing.path[-1] != attachment.node or packet.selected_locator != attachment.locator:
        return EndpointDeliveryResult("wrong_attachment", routing)
    return EndpointDeliveryResult(attachment.deliver(packet.destination_eid, packet.payload), routing)


@dataclass
class MockAssociation:
    """Upper-layer test state keyed externally by remote EID; not a network Channel."""

    remote_eid: EndpointID
    upper_state: dict[str, int] = field(default_factory=dict)
    binding: EndpointBinding | None = None
    selected_locator: Locator | None = None
    program: RouteProgram | None = None

    def replace_delivery(self, binding: EndpointBinding, locator: Locator, program: RouteProgram) -> bool:
        """Replace delivery material without changing peer or upper-layer state."""
        if binding.eid != self.remote_eid:
            raise ValueError("delivery binding belongs to a different remote EID")
        if self.binding is not None and binding.version < self.binding.version:
            return False
        if self.binding is not None and binding.version == self.binding.version and binding != self.binding:
            raise ValueError("one BindingVersion cannot identify conflicting records")
        if locator not in binding.locators or locator != program.destination:
            raise ValueError("selected Locator must be in the binding and match the Route Program")
        self.binding = binding
        self.selected_locator = locator
        self.program = program
        return True
