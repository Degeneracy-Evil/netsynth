"""Tiny adversarial proof-binding and endpoint AEAD checks, no crypto benchmark."""

from copy import deepcopy
from dataclasses import FrozenInstanceError, replace

import pytest

from netsynth.scale5 import EndpointBinding, EndpointID
from netsynth.scale6 import ChannelPacket, Fragment, ReceiveToken
from netsynth.security_floor import (
    AuthenticationProof,
    IdentityAnchor,
    ProtectedEnvelope,
    SignedBinding,
    VerifiedBindingCache,
    authenticate_transcript,
    binding_statement,
    delegate,
    establish_protected_channel,
    sign_binding,
    verify_binding,
    verify_establishment,
    verify_role,
)
from netsynth.security_floor_probe import SecurityFixture, fixture_signing_key, run_probe


def test_all_thirteen_security_floor_criteria_reproducibly() -> None:
    result = run_probe()
    criteria = result["criteria"]
    assert isinstance(criteria, dict) and len(criteria) == 13
    assert all(value is True for value in criteria.values())
    assert result == run_probe()


def test_immutable_anchor_and_role_rotation_without_directory() -> None:
    f = SecurityFixture()
    anchor = f.right_auth.proof.anchor
    assert IdentityAnchor(anchor.root_public_key).eid == f.right_eid
    with pytest.raises(FrozenInstanceError):
        anchor.root_public_key = b"mutated"  # type: ignore[misc]
    rotated = delegate(f.right_root, fixture_signing_key("rotated-binding"), "BINDING_UPDATE", generation=2)
    record = sign_binding(EndpointBinding(f.right_eid, 2, frozenset({f.new_locator}), 10), rotated, 2)
    # An unrelated new client gets only the object and self-contained public proof.
    client = VerifiedBindingCache()
    assert client.accept(record, 2)
    assert client.bindings[f.right_eid] == record.binding
    assert rotated.proof.anchor.eid == anchor.eid
    other = SecurityFixture("new-channel")
    rotated_auth = delegate(f.right_root, fixture_signing_key("rotated-auth"), "CHANNEL_AUTH", generation=2)
    new_proof = authenticate_transcript(other.transcript, rotated_auth, 2)
    a, b = establish_protected_channel(
        other.transcript, other.left_proof, new_proof, other.left_ephemeral, other.right_ephemeral, 2
    )
    assert b.channel.local_eid == f.right_eid
    assert a._send_key == b._receive_key and b._send_key == a._receive_key
    assert a._send_key != f.a._send_key and a._send_key != a._receive_key


@pytest.mark.parametrize("field_name", ["role", "generation", "public_key", "not_before", "not_after", "signature"])
def test_modified_root_delegation_is_rejected(field_name: str) -> None:
    f = SecurityFixture()
    proof = f.right_binding.proof
    credential = proof.credential
    match field_name:
        case "role":
            changed = replace(credential, role="CHANNEL_AUTH")
        case "generation":
            changed = replace(credential, generation=2)
        case "public_key":
            changed = replace(credential, public_key=f.left_auth.proof.credential.public_key)
        case "not_before":
            changed = replace(credential, not_before=1)
        case "not_after":
            changed = replace(credential, not_after=200)
        case _:
            changed = replace(credential, root_signature=b"forged")
    with pytest.raises(ValueError):
        verify_role(replace(proof, credential=changed), f.right_eid, "BINDING_UPDATE", 2)


def test_role_time_key_possession_and_claimed_anchor_checks() -> None:
    f = SecurityFixture()
    with pytest.raises(ValueError, match="role"):
        sign_binding(f.initial.binding, f.right_auth, 2)
    with pytest.raises(ValueError, match="inactive"):
        verify_role(f.right_binding.proof, f.right_eid, "BINDING_UPDATE", 100)
    future = delegate(f.right_root, fixture_signing_key("future"), "BINDING_UPDATE", not_before=10, not_after=20)
    with pytest.raises(ValueError, match="inactive"):
        verify_role(future.proof, f.right_eid, "BINDING_UPDATE", 9)
    with pytest.raises(ValueError, match="private key"):
        replace(f.right_binding, private_key=f.left_auth.private_key).sign(b"operation")
    with pytest.raises(ValueError, match="Anchor"):
        verify_role(replace(f.right_auth.proof, anchor=f.left_auth.proof.anchor), f.right_eid, "CHANNEL_AUTH", 2)
    with pytest.raises(ValueError, match="Anchor"):
        verify_role(f.right_auth.proof, EndpointID(b"claimed-stranger"), "CHANNEL_AUTH", 2)


@pytest.mark.parametrize("field_name", ["version", "locators", "lifetime", "eid", "signature", "proof"])
def test_untrusted_binding_contents_fail_independent_client_verification(field_name: str) -> None:
    f = SecurityFixture()
    signed = f.initial
    match field_name:
        case "version":
            forged = replace(signed, binding=replace(signed.binding, version=2))
        case "locators":
            forged = replace(signed, binding=replace(signed.binding, locators=frozenset({f.new_locator})))
        case "lifetime":
            forged = replace(signed, binding=replace(signed.binding, cache_lifetime=999))
        case "eid":
            forged = replace(signed, binding=replace(signed.binding, eid=f.left_eid))
        case "signature":
            forged = replace(signed, signature=b"forged")
        case _:
            forged = replace(signed, proof=f.left_auth.proof)
    f.store.records[f.right_eid] = forged
    before = deepcopy(f.cache.bindings)
    with pytest.raises(ValueError):
        f.cache.accept(f.store.records[f.right_eid], 2)
    assert f.cache.bindings == before
    with pytest.raises(ValueError):
        f.store.publish(forged, 2)


def test_known_rollback_conflict_and_first_contact_staleness_are_distinct() -> None:
    f = SecurityFixture()
    record = sign_binding(
        replace(f.initial.binding, version=2, locators=frozenset({f.new_locator})), f.right_binding, 2
    )
    assert f.cache.accept(record, 2)
    assert not f.cache.accept(f.initial, 2)
    assert not f.cache.accept(record, 2)
    conflict = sign_binding(replace(record.binding, locators=frozenset({f.old_locator})), f.right_binding, 2)
    with pytest.raises(ValueError, match="conflicting"):
        f.cache.accept(conflict, 2)
    assert f.cache.bindings[f.right_eid] == record.binding
    first_contact = VerifiedBindingCache()
    assert first_contact.accept(f.initial, 2)  # Signature proves authenticity, not latest freshness.
    assert f.store.publish(record, 2)
    assert not f.store.publish(f.initial, 2)
    assert f.store.records[f.right_eid] == record
    wrong_role = SignedBinding(record.binding, f.right_auth.proof, f.right_auth.sign(binding_statement(record.binding)))
    with pytest.raises(ValueError, match="role"):
        verify_binding(wrong_role, 2)


@pytest.mark.parametrize(
    "field_name",
    [
        "left_eid",
        "right_eid",
        "left_token",
        "right_token",
        "left_ephemeral",
        "right_ephemeral",
        "context",
        "message_size",
        "capacity",
    ],
)
def test_establishment_binds_complete_context_not_locator(field_name: str) -> None:
    f = SecurityFixture()
    transcript = f.transcript
    match field_name:
        case "left_eid":
            changed = replace(transcript, left_eid=f.right_eid)
        case "right_eid":
            changed = replace(transcript, right_eid=f.left_eid)
        case "left_token":
            changed = replace(transcript, left_token=ReceiveToken(b"swapped-left"))
        case "right_token":
            changed = replace(transcript, right_token=ReceiveToken(b"swapped-right"))
        case "left_ephemeral":
            changed = replace(transcript, left_ephemeral=transcript.right_ephemeral)
        case "right_ephemeral":
            changed = replace(transcript, right_ephemeral=transcript.left_ephemeral)
        case "context":
            changed = replace(transcript, context="downgrade")
        case "message_size":
            changed = replace(transcript, maximum_message_size=8)
        case _:
            changed = replace(transcript, right_capacity=32)
    with pytest.raises(ValueError):
        verify_establishment(changed, f.left_proof, f.right_proof, 2)


def test_establishment_requires_both_correct_role_and_private_ephemeral_possession() -> None:
    f = SecurityFixture()
    wrong = AuthenticationProof(f.right_binding.proof, f.right_binding.sign(f.transcript.canonical_bytes()))
    with pytest.raises(ValueError, match="role"):
        verify_establishment(f.transcript, f.left_proof, wrong, 2)
    with pytest.raises(ValueError, match="Anchor"):
        verify_establishment(f.transcript, f.right_proof, f.right_proof, 2)
    other = SecurityFixture("another")
    with pytest.raises(ValueError, match="ephemeral private"):
        establish_protected_channel(
            f.transcript, f.left_proof, f.right_proof, other.left_ephemeral, f.right_ephemeral, 2
        )


@pytest.mark.parametrize("field_name", ["data", "control", "token", "packet_number", "incarnation", "direction"])
def test_protected_packet_tampering_fails_before_transport_mutation(field_name: str) -> None:
    f = SecurityFixture()
    f.a.channel.queue_message(b"hello")
    packet = f.send(2)
    recipient = f.b
    if field_name == "control":
        assert f.deliver(packet, 3) == "accepted"
        packet = f.b.protect(f.b.channel.make_feedback())
        recipient = f.a
    match field_name:
        case "token":
            bad = replace(packet, receive_token=ReceiveToken(b"tampered"))
        case "packet_number":
            bad = replace(packet, packet_number=packet.packet_number + 1)
        case "incarnation":
            recipient = SecurityFixture("new-incarnation").b
            bad = packet
        case "direction":
            recipient = f.a
            bad = packet
        case _:
            bad = replace(packet, ciphertext=packet.ciphertext[:-1] + bytes([packet.ciphertext[-1] ^ 1]))
    before = deepcopy(vars(recipient.channel))
    assert recipient.receive(ProtectedEnvelope(bad), 4) == "authentication_failed"
    assert vars(recipient.channel) == before


def test_transit_mark_mutable_peer_echo_authenticated_and_replay_safe() -> None:
    f = SecurityFixture()
    f.a.channel.queue_message(b"hello")
    packet = f.send(2)
    envelope = ProtectedEnvelope(packet)
    assert envelope.mark_congestion().mark_congestion() == envelope.mark_congestion()
    assert envelope.packet.ciphertext == envelope.mark_congestion().packet.ciphertext
    assert f.b.receive(envelope, 3) == "accepted"
    assert f.b.receive(envelope.mark_congestion(), 4) == "duplicate"
    assert f.b.channel.completed == {0: b"hello"} and f.b.channel.delivery_order == [0]
    feedback = f.b.protect(f.b.channel.make_feedback())
    before = deepcopy(vars(f.a.channel))
    forged = replace(feedback, ciphertext=feedback.ciphertext[:-1] + bytes([feedback.ciphertext[-1] ^ 1]))
    assert f.a.receive(ProtectedEnvelope(forged), 5) == "authentication_failed"
    assert vars(f.a.channel) == before
    assert f.a.receive(ProtectedEnvelope(feedback), 5) == "accepted"
    assert f.a.channel.active_path.congestion_marks == 1
    window = f.a.channel.active_path.congestion_window
    assert f.a.receive(ProtectedEnvelope(feedback), 6) == "duplicate"
    assert f.a.channel.active_path.congestion_window == window


def test_nonce_reuse_is_blocked_and_retransmission_uses_fresh_number() -> None:
    f = SecurityFixture()
    message = f.a.channel.queue_message(b"hello")
    old = f.send(2)
    original = f.a.channel.sent_packets[old.packet_number].packet
    assert f.a.protect(original) == old  # Cached exact ciphertext, not new encryption.
    altered = ChannelPacket.create(
        f.left_eid,
        f.right_eid,
        f.b.channel.local_receive_token,
        original.packet_number,
        Fragment(message, 5, 0, b"wrong"),
    )
    with pytest.raises(ValueError, match="different content"):
        f.a.protect(altered)
    f.a.channel.mark_lost(original.packet_number)
    new = f.send(3)
    assert new.packet_number > old.packet_number and new.ciphertext != old.ciphertext
    assert f.deliver(new, 4) == "accepted"
    assert f.deliver(old, 5) == "accepted"
    assert f.b.channel.delivery_order == [message]
    assert f.a.receive(ProtectedEnvelope(f.b.protect(f.b.channel.make_feedback())), 6) == "accepted"
    assert f.a.channel.messages[message].acknowledged == set(range(5))


def test_migration_preserves_keys_channel_identity_and_key_free_routing() -> None:
    f = SecurityFixture()
    routing = f.routing_snapshot()
    channel = f.a.channel
    tokens = (channel.local_receive_token, channel.remote_receive_token)
    key_identity = (f.a.incarnation, f.a._send_key, f.a._receive_key)
    f.a.channel.queue_message(b"before")
    packet = f.send(2)
    assert f.deliver(packet, 3) == "accepted"
    rotated = delegate(f.right_root, fixture_signing_key("moved-update"), "BINDING_UPDATE", generation=2)
    f.migrate(rotated, 4)
    assert f.a.channel is channel
    assert (f.a.incarnation, f.a._send_key, f.a._receive_key) == key_identity
    assert (channel.local_receive_token, channel.remote_receive_token) == tokens
    assert channel.active_path.program.destination == f.new_locator and channel.remote_eid == f.right_eid
    assert f.a.receive(ProtectedEnvelope(f.b.protect(f.b.channel.make_feedback())), 5) == "accepted"
    assert channel.paths[0].confirmed and not channel.active_path.confirmed
    assert f.routing_snapshot() == routing
    for obj in (f.tree, f.service, f.transit, channel.active_path.program):
        assert not any(
            word in name for name in vars(obj) for word in ("credential", "private_key", "traffic_key", "anchor")
        )
    f.a.channel.queue_message(b"after")
    moved = f.send(6)
    assert f.deliver(moved, 7) == "accepted"
    assert f.b.channel.completed == {0: b"before", 1: b"after"}
