"""Tiny adversarial checks for identity above the frozen Scale-4 substrate."""

from dataclasses import fields

import pytest

from netsynth.forwarding import Locator
from netsynth.scale4 import AccessHandle, PathletHandle, PhysicalHop, execute_route_program
from netsynth.scale5 import (
    BindingResolver,
    BindingService,
    Endpoint,
    EndpointBinding,
    EndpointID,
    EndpointPacket,
    LocalAttachment,
    MockAssociation,
    deliver_endpoint_packet,
)
from netsynth.scale5_probe import TinyAttachmentFixture, run_probe


def test_adversarial_probe_meets_all_ten_freeze_criteria_reproducibly() -> None:
    probe = run_probe()
    criteria = probe["criteria"]
    assert isinstance(criteria, dict)
    assert len(criteria) == 11
    assert all(value is True for value in criteria.values())
    assert probe == run_probe()


def test_empty_binding_is_distinct_from_unknown_and_version_is_per_eid() -> None:
    old, new = Locator((1,), 0), Locator((1,), 1)
    service = BindingService((old, new))
    resolver = BindingResolver(old, service)
    mobile, other, unknown = EndpointID(b"mobile"), EndpointID(b"other"), EndpointID(b"unknown")
    authority = service.authority_index(mobile)
    assert resolver.resolve(unknown) is None
    assert service.last_read_locator == service.authority_locators[service.authority_index(unknown)]
    first = service.publish(mobile, frozenset({old}))
    disconnected = service.publish(mobile, frozenset())
    reattached = service.publish(mobile, frozenset({new}))
    other_binding = service.publish(other, frozenset({new}))
    assert [first.version, disconnected.version, reattached.version] == [1, 2, 3]
    assert first.eid == disconnected.eid == reattached.eid
    assert disconnected.locators == frozenset()
    assert other_binding.version == 1
    assert service.authority_index(mobile) == authority
    assert service.record_count == 2
    resolver.accept(disconnected)
    assert resolver.resolve(mobile) == disconnected
    assert resolver.resolve_fresh(mobile) == reattached


def test_one_eid_delivers_at_both_simultaneous_locators() -> None:
    fixture = TinyAttachmentFixture()
    endpoint = Endpoint(EndpointID(b"multihomed"))
    service = BindingService((fixture.old_locator, fixture.new_locator))
    binding = service.publish(endpoint.eid, frozenset({fixture.old_locator, fixture.new_locator}))
    for locator, node in ((fixture.old_locator, 3), (fixture.new_locator, 4)):
        attachment = LocalAttachment(locator, node)
        attachment.attach(endpoint)
        program, access, context = fixture.compile_attachment(locator, f"multi-{node}")
        result = deliver_endpoint_packet(
            fixture.graph,
            fixture.registries,
            access,
            context,
            10,
            EndpointPacket(binding.eid, locator, program, b"same endpoint"),
            attachment,
        )
        assert result.status == "delivered"
    assert endpoint.inbox == [b"same endpoint", b"same endpoint"]


def test_stale_cache_reaches_reused_position_then_explicit_fresh_lookup_recovers() -> None:
    fixture = TinyAttachmentFixture()
    snapshot = fixture.routing_snapshot()
    service = BindingService((fixture.old_locator, fixture.new_locator))
    resolver = BindingResolver(fixture.old_locator, service)
    uninformed_resolver = BindingResolver(fixture.new_locator, service)
    endpoint, replacement = Endpoint(EndpointID(b"moving")), Endpoint(EndpointID(b"replacement"))
    old, new = LocalAttachment(fixture.old_locator, 3), LocalAttachment(fixture.new_locator, 4)
    old.attach(endpoint)
    first = service.publish(endpoint.eid, frozenset({old.locator}))
    assert resolver.resolve(endpoint.eid) == first
    assert uninformed_resolver.resolve(endpoint.eid) == first
    program, access, context = fixture.compile_attachment(old.locator, "cached")
    associations = {endpoint.eid: MockAssociation(endpoint.eid, {"progress": 42})}
    association = associations[endpoint.eid]
    assert association.replace_delivery(first, old.locator, program)
    upper_state = association.upper_state

    old.detach(endpoint.eid)
    old.attach(replacement)
    new.attach(endpoint)
    current = service.publish(endpoint.eid, frozenset({new.locator}))
    reads = service.read_count
    assert resolver.resolve(endpoint.eid) == first
    assert service.read_count == reads
    packet = EndpointPacket(endpoint.eid, old.locator, program, b"stale")
    stale = deliver_endpoint_packet(fixture.graph, fixture.registries, access, context, 10, packet, old)
    assert stale.routing.status == "delivered"
    assert stale.routing.path[-1] == old.node
    assert stale.status == "eid_absent"
    assert not endpoint.inbox and not replacement.inbox

    if stale.status == "eid_absent":
        refreshed = resolver.resolve_fresh(endpoint.eid, first.version)
    else:
        pytest.fail("stale final EID rejection must force a fresh lookup")
    assert refreshed == current
    assert service.read_count == reads + 1
    new_program, new_access, new_context = fixture.compile_attachment(min(refreshed.locators), "refreshed")
    assert association.replace_delivery(refreshed, new.locator, new_program)
    recovered = deliver_endpoint_packet(
        fixture.graph,
        fixture.registries,
        new_access,
        new_context,
        10,
        EndpointPacket(endpoint.eid, new.locator, new_program, b"fresh"),
        new,
    )
    assert recovered.status == "delivered"
    assert endpoint.inbox == [b"fresh"] and not replacement.inbox
    assert new_program.destination != program.destination
    assert associations[endpoint.eid] is association
    assert association.remote_eid == endpoint.eid
    assert association.upper_state is upper_state and upper_state == {"progress": 42}
    assert not association.replace_delivery(first, old.locator, program)
    assert uninformed_resolver.resolve(endpoint.eid) == first
    assert fixture.routing_snapshot() == snapshot


def test_delayed_cache_responses_cannot_regress_or_extend_lifetime() -> None:
    locator = Locator((), 0)
    service = BindingService((locator,))
    resolver = BindingResolver(locator, service)
    eid = EndpointID(b"versions")
    first = service.publish(eid, frozenset({locator}), cache_lifetime=2)
    second = service.publish(eid, frozenset(), cache_lifetime=2)
    assert resolver.accept(second)
    assert not resolver.accept(first)
    resolver.advance(1)
    assert not resolver.accept(second)
    resolver.advance(1)
    reads = service.read_count
    assert resolver.resolve(eid) == second
    assert service.read_count == reads + 1
    assert not resolver.accept(first)
    conflicting = EndpointBinding(eid, second.version, first.locators, 2)
    with pytest.raises(ValueError, match="conflicting"):
        resolver.accept(conflicting)
    ahead = EndpointBinding(eid, 10, first.locators, 2)
    assert resolver.accept(ahead)
    with pytest.raises(ValueError, match="older"):
        resolver.resolve_fresh(eid)


def test_locator_infrastructure_and_transit_state_need_no_eid_resolution() -> None:
    fixture = TinyAttachmentFixture()
    # These infrastructure programs execute before any Binding Service exists.
    for locator in (fixture.old_locator, fixture.new_locator):
        program, access, context = fixture.compile_attachment(locator, f"infrastructure-{locator.selector}")
        result = execute_route_program(fixture.graph, fixture.registries, access, program, context, 10)
        assert result.status == "delivered"
        assert all(isinstance(action, (PhysicalHop, PathletHandle, AccessHandle)) for action in program.actions)
        assert all("eid" not in record.name for record in fields(program))
        assert all("eid" not in key for key in vars(fixture.service))
        assert all("eid" not in key for key in vars(fixture.transit))
    service = BindingService((fixture.old_locator, fixture.new_locator))
    resolver = BindingResolver(fixture.old_locator, service)
    assert resolver.locator == fixture.old_locator
    assert service.authority_locators == (fixture.old_locator, fixture.new_locator)
    assert service.read_count == 0 and service.record_count == 0
    eid = EndpointID(b"bootstrap-query")
    service.publish(eid, frozenset({fixture.new_locator}))
    assert resolver.resolve(eid) is not None
    assert service.last_read_locator == service.authority_locators[service.authority_index(eid)]
    assert service.read_count == 1  # One query, no recursive resolver EID lookup.


def test_local_exact_eid_demultiplexing_and_route_failures_do_not_deliver() -> None:
    fixture = TinyAttachmentFixture()
    program, access, context = fixture.compile_attachment(fixture.old_locator, "failure")
    attachment = LocalAttachment(fixture.old_locator, 3)
    a, b = Endpoint(EndpointID(b"a")), Endpoint(EndpointID(b"b"))
    attachment.attach(a)
    attachment.attach(b)
    assert attachment.deliver(a.eid, b"for a") == "delivered"
    assert a.inbox == [b"for a"] and not b.inbox
    packet = EndpointPacket(b.eid, attachment.locator, program, b"for b")
    failed = deliver_endpoint_packet(fixture.graph, fixture.registries, access, context, 0, packet, attachment)
    assert failed.status == "routing_failure"
    assert failed.routing.status == "hop_budget_exhausted"
    assert not b.inbox
    wrong = LocalAttachment(fixture.new_locator, 4)
    wrong.attach(b)
    misdirected = deliver_endpoint_packet(fixture.graph, fixture.registries, access, context, 10, packet, wrong)
    assert misdirected.status == "wrong_attachment" and not b.inbox
    with pytest.raises(ValueError, match="selected Locator"):
        EndpointPacket(b.eid, fixture.new_locator, program, b"bad envelope")


def test_sharding_is_flat_and_endpoint_identity_has_no_locator_fields() -> None:
    locators = (Locator((0,), 0), Locator((1,), 0))
    service = BindingService(locators)
    eids = [EndpointID(index.to_bytes(2)) for index in range(8)]
    assert {service.authority_index(eid) for eid in eids} == {0, 1}
    for eid in eids:
        service.publish(eid, frozenset({locators[0]}))
    assert service.record_count == 8
    assert [record.name for record in fields(EndpointID)] == ["value"]
    generated = EndpointID.generate()
    assert generated.value and isinstance(generated.value, bytes)
