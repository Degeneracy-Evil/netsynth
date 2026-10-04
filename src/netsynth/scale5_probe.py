"""Five-node adversarial fixture for Scale-5 semantic validation only."""

from __future__ import annotations

from types import MappingProxyType

from netsynth.decomposition import Scope, ScopeTree
from netsynth.forwarding import Locator
from netsynth.graph import Edge, Graph
from netsynth.scale4 import (
    AccessHandle,
    AccessRealization,
    AccessRegistry,
    AdvertisedPathlet,
    BoundaryTransitGraph,
    CrossingLink,
    DestinationAccessOffer,
    PathletHandle,
    PathletRegistry,
    PhysicalHop,
    RouteProgram,
    RouteQueryContext,
    ScopedTransitPathlet,
    ScopeRouteService,
    SourceAccessOffer,
    execute_route_program,
)
from netsynth.scale5 import (
    BindingResolver,
    BindingService,
    Endpoint,
    EndpointID,
    EndpointPacket,
    LocalAttachment,
    MockAssociation,
    deliver_endpoint_packet,
)


class TinyAttachmentFixture:
    """Fixed test topology; not an architectural routing interface or algorithm."""

    def __init__(self) -> None:
        self.graph = Graph(set(range(5)), [Edge(node, node + 1) for node in range(4)])
        self.tree = ScopeTree(
            Scope(
                "root",
                self.graph.nodes,
                (
                    Scope("source", frozenset({0})),
                    Scope("transit", frozenset({1, 2})),
                    Scope("target", frozenset({3, 4})),
                ),
            )
        )
        self.tree.validate(self.graph)
        self.old_locator = Locator((2,), 0)
        self.new_locator = Locator((2,), 1)
        self.transit = PathletRegistry("transit", frozenset({PhysicalHop(1, 2), PhysicalHop(2, 1)}))
        self.handles = (PathletHandle("transit", 0, 0), PathletHandle("transit", 1, 0))
        for handle, ingress, egress in ((self.handles[0], 1, 2), (self.handles[1], 2, 1)):
            self.transit.publish(
                ScopedTransitPathlet(AdvertisedPathlet(handle, ingress, egress, 1.0), (PhysicalHop(ingress, egress),))
            )
        self.registries = MappingProxyType({"transit": self.transit})
        self.service = ScopeRouteService(
            "root",
            ("source", "transit", "target"),
            {0: "source", 1: "transit", 2: "transit", 3: "target"},
            (
                BoundaryTransitGraph("source", frozenset({0}), ()),
                self.transit.export(frozenset({1, 2})),
                BoundaryTransitGraph("target", frozenset({3}), ()),
            ),
            (CrossingLink(0, 1, 1.0), CrossingLink(2, 3, 1.0)),
        )

    def compile_attachment(
        self, locator: Locator, query_id: str
    ) -> tuple[RouteProgram, MappingProxyType[str, AccessRegistry], RouteQueryContext]:
        """Use fixed owner-local access paths; the parent never receives them."""
        # Only the target owner knows this two-entry local Locator-to-position map.
        target = {self.old_locator: 3, self.new_locator: 4}[locator]
        actions = () if target == 3 else (PhysicalHop(3, 4),)
        source_offer = SourceAccessOffer(0, 0.0, AccessHandle("source", query_id, 0))
        target_offer = DestinationAccessOffer(3, float(len(actions)), AccessHandle("target", query_id, 0))
        source_access = AccessRegistry("source", query_id, frozenset({0}), frozenset())
        source_access.publish_source(source_offer, AccessRealization(0, 0, ()))
        target_access = AccessRegistry(
            "target",
            query_id,
            frozenset({3}),
            frozenset({PhysicalHop(3, 4)}),
            destination=locator,
            destination_node=target,
        )
        target_access.publish_destination(target_offer, AccessRealization(3, target, actions))
        compiled = self.service.compile(query_id, locator, (source_offer,), (target_offer,))
        if compiled is None:
            raise AssertionError("fixed fixture must have a route to both attachments")
        return (
            compiled.program,
            MappingProxyType({"source": source_access, "target": target_access}),
            RouteQueryContext(query_id, 0),
        )

    def routing_snapshot(self) -> tuple[object, ...]:
        """Audit structural routing state without any endpoint/binding input."""
        return (
            self.tree,
            self.service.scope_id,
            self.service.immediate_child_ids,
            dict(self.service.boundary_owner),
            self.service.child_btgs,
            self.service.crossings,
            tuple(self.transit.lookup(handle) for handle in self.handles),
            self.transit.persistent_records,
            self.service.persistent_records,
        )


def run_probe() -> dict[str, object]:
    """Move one Endpoint, reuse its old attachment, and recover via a fresh read."""
    fixture = TinyAttachmentFixture()
    before = fixture.routing_snapshot()
    old_program, old_access, old_context = fixture.compile_attachment(fixture.old_locator, "old")
    infrastructure = execute_route_program(fixture.graph, fixture.registries, old_access, old_program, old_context, 10)
    service = BindingService((fixture.old_locator, fixture.new_locator))
    resolver = BindingResolver(fixture.old_locator, service)
    other_resolver = BindingResolver(fixture.new_locator, service)
    mobile = Endpoint(EndpointID(b"opaque-mobile"))
    replacement = Endpoint(EndpointID(b"opaque-replacement"))
    old = LocalAttachment(fixture.old_locator, 3)
    new = LocalAttachment(fixture.new_locator, 4)
    old.attach(mobile)
    initial = service.publish(mobile.eid, frozenset({old.locator}))
    resolver.resolve(mobile.eid)
    other_resolver.resolve(mobile.eid)
    owner_index = service.authority_index(mobile.eid)
    associations = {mobile.eid: MockAssociation(mobile.eid, {"mock_progress": 7})}
    association = associations[mobile.eid]
    association.replace_delivery(initial, old.locator, old_program)
    initial_delivery = deliver_endpoint_packet(
        fixture.graph,
        fixture.registries,
        old_access,
        old_context,
        10,
        EndpointPacket(mobile.eid, old.locator, old_program, b"before move"),
        old,
    )
    new.attach(mobile)
    overlap = service.publish(mobile.eid, frozenset({old.locator, new.locator}))
    old.detach(mobile.eid)
    old.attach(replacement)
    current = service.publish(mobile.eid, frozenset({new.locator}))
    cached = resolver.resolve(mobile.eid)
    stale_delivery = deliver_endpoint_packet(
        fixture.graph,
        fixture.registries,
        old_access,
        old_context,
        10,
        EndpointPacket(mobile.eid, old.locator, old_program, b"stale attempt"),
        old,
    )
    if stale_delivery.status != "eid_absent":
        raise AssertionError("old attachment must reject the moved EID")
    fresh = resolver.resolve_fresh(mobile.eid, initial.version)
    if fresh is None or not fresh.locators:
        raise AssertionError("mobile Endpoint must have a current attachment")
    selected = min(fresh.locators)
    new_program, new_access, new_context = fixture.compile_attachment(selected, "fresh")
    association.replace_delivery(fresh, selected, new_program)
    recovered = deliver_endpoint_packet(
        fixture.graph,
        fixture.registries,
        new_access,
        new_context,
        10,
        EndpointPacket(mobile.eid, selected, new_program, b"after fresh lookup"),
        new,
    )
    rejected_older = not resolver.accept(initial)
    return {
        "schema": "netsynth.scale5.semantic-probe.v1",
        "topology": fixture.graph.to_dict(),
        "parameters": {
            "seed": None,
            "generator": "hand-built-five-node-chain",
            "scope_children": fixture.service.immediate_child_ids,
            "authority_groups": 2,
            "sharding": "sha256-modulo-fixed-groups-toy",
            "cache_lifetime_ticks": 10,
            "locator_selection": "smallest-current-locator-fixture-policy",
        },
        "results": {
            "initial_delivery": initial_delivery.status,
            "stale_delivery": stale_delivery.status,
            "stale_physical_path": stale_delivery.routing.path,
            "fresh_delivery": recovered.status,
            "fresh_physical_path": recovered.routing.path,
            "binding_versions": [initial.version, overlap.version, current.version],
            "sequential_header_length": new_program.sequential_header_length,
            "maximum_stack_depth": recovered.routing.maximum_stack_depth,
        },
        "criteria": {
            "stable_eid": initial.eid == overlap.eid == current.eid == mobile.eid,
            "simultaneous_locators": overlap.locators == frozenset({old.locator, new.locator}),
            "movement_preserves_scale4": before == fixture.routing_snapshot(),
            "stale_never_delivers_to_replacement": stale_delivery.status == "eid_absent" and not replacement.inbox,
            "fresh_lookup_recompiles": recovered.status == "delivered" and new_program != old_program,
            "older_cache_response_rejected": rejected_older and resolver.resolve(mobile.eid) == current,
            "no_global_invalidation": cached == initial and other_resolver.resolve(mobile.eid) == initial,
            "resolver_bootstrap_by_locator": (
                resolver.locator == old_program.destination
                and service.last_read_locator == service.authority_locators[owner_index]
            ),
            "association_survives": associations[mobile.eid] is association
            and association.upper_state == {"mock_progress": 7},
            "locator_only_traffic": infrastructure.status == "delivered",
            "authority_independent_of_attachment": service.authority_index(mobile.eid) == owner_index,
        },
        "state_records": {
            "binding_authority": service.record_count,
            "resolver_caches": resolver.cache_record_count + other_resolver.cache_record_count,
            "local_endpoint_delivery": old.record_count + new.record_count,
            "mock_associations": len(associations),
            "transit_eid_records": 0,
        },
    }
