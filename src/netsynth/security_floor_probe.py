"""Deterministic security-floor fixture; all embedded test secrets are public, NOT deployable."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from functools import partial
from hashlib import sha256

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

from netsynth.scale5 import Endpoint, EndpointBinding, EndpointPacket, LocalAttachment, deliver_endpoint_packet
from netsynth.scale5_probe import TinyAttachmentFixture
from netsynth.scale5_probe import run_probe as scale5_probe
from netsynth.scale6 import ReceiveToken
from netsynth.security_floor import (
    AuthenticationProof,
    EstablishmentTranscript,
    IdentityAnchor,
    OperationalSigner,
    ProtectedEnvelope,
    ProtectedPacket,
    SignedBindingStore,
    VerifiedBindingCache,
    authenticate_transcript,
    delegate,
    establish_protected_channel,
    sign_binding,
    verify_binding,
    verify_establishment,
    verify_role,
)


def fixture_signing_key(label: str) -> Ed25519PrivateKey:
    """Known deterministic secrets exclusively for reproducible tests."""
    return Ed25519PrivateKey.from_private_bytes(sha256(label.encode()).digest())


def rejects(operation: Callable[[], object]) -> bool:
    try:
        operation()
    except ValueError:
        return True
    return False


class SecurityFixture(TinyAttachmentFixture):
    """One reused five-node physical graph, two identities, no security state in routing."""

    def __init__(self, incarnation_label: str = "first") -> None:
        super().__init__()
        self.left_root, self.right_root = fixture_signing_key("left-root"), fixture_signing_key("right-root")
        self.left_auth = delegate(self.left_root, fixture_signing_key("left-auth"), "CHANNEL_AUTH")
        self.right_auth = delegate(self.right_root, fixture_signing_key("right-auth"), "CHANNEL_AUTH")
        self.right_binding = delegate(self.right_root, fixture_signing_key("right-binding"), "BINDING_UPDATE")
        self.left_eid, self.right_eid = self.left_auth.proof.anchor.eid, self.right_auth.proof.anchor.eid
        self.left_ephemeral = X25519PrivateKey.from_private_bytes(
            sha256(f"left-ephemeral-{incarnation_label}".encode()).digest()
        )
        self.right_ephemeral = X25519PrivateKey.from_private_bytes(
            sha256(f"right-ephemeral-{incarnation_label}".encode()).digest()
        )
        self.transcript = EstablishmentTranscript(
            self.left_eid,
            self.right_eid,
            ReceiveToken(sha256(f"left-token-{incarnation_label}".encode()).digest()),
            ReceiveToken(sha256(f"right-token-{incarnation_label}".encode()).digest()),
            self.left_ephemeral.public_key().public_bytes_raw(),
            self.right_ephemeral.public_key().public_bytes_raw(),
            16,
            64,
            64,
        )
        self.left_proof = authenticate_transcript(self.transcript, self.left_auth, 1)
        self.right_proof = authenticate_transcript(self.transcript, self.right_auth, 1)
        self.a, self.b = establish_protected_channel(
            self.transcript, self.left_proof, self.right_proof, self.left_ephemeral, self.right_ephemeral, 1
        )
        self.remote = Endpoint(self.right_eid)
        self.old_attachment, self.new_attachment = (
            LocalAttachment(self.old_locator, 3),
            LocalAttachment(self.new_locator, 4),
        )
        self.old_attachment.attach(self.remote)
        self.store, self.cache = SignedBindingStore(), VerifiedBindingCache()
        self.initial = sign_binding(
            EndpointBinding(self.right_eid, 1, frozenset({self.old_locator}), 10), self.right_binding, 1
        )
        self.store.publish(self.initial, 1)
        self.cache.accept(self.store.records[self.right_eid], 1)
        program, self.access, self.context = self.compile_attachment(self.old_locator, "security-first")
        self.a.channel.replace_path(self.cache.bindings[self.right_eid], program, 96, 1)

    def send(self, now: int) -> ProtectedPacket:
        packet = self.a.channel.send_next(now)
        if packet is None:
            raise AssertionError("fixture requires one eligible fragment")
        return self.a.protect(packet)

    def deliver(self, protected: ProtectedPacket, now: int, mark: bool = False) -> str:
        program = self.a.channel.active_path.program
        attachment = self.new_attachment if program.destination == self.new_locator else self.old_attachment
        result = deliver_endpoint_packet(
            self.graph,
            self.registries,
            self.access,
            self.context,
            10,
            EndpointPacket(self.right_eid, program.destination, program, protected.ciphertext),
            attachment,
        )
        if result.status != "delivered":
            return result.status
        envelope = ProtectedEnvelope(protected)
        if mark:
            envelope = envelope.mark_congestion()
        return self.b.receive(envelope, now)

    def migrate(self, signer: OperationalSigner, now: int) -> None:
        self.old_attachment.detach(self.right_eid)
        self.new_attachment.attach(self.remote)
        record = sign_binding(EndpointBinding(self.right_eid, 2, frozenset({self.new_locator}), 10), signer, now)
        self.store.publish(record, now)
        self.cache.accept(self.store.records[self.right_eid], now)
        program, self.access, self.context = self.compile_attachment(self.new_locator, "security-moved")
        self.a.channel.replace_path(self.cache.bindings[self.right_eid], program, 100, now)


def run_probe() -> dict[str, object]:
    fixture = SecurityFixture()
    before = fixture.routing_snapshot()
    a, b = fixture.a, fixture.b
    rotated_binding = delegate(
        fixture.right_root, fixture_signing_key("right-binding-rotated"), "BINDING_UPDATE", generation=2
    )
    rotated_auth = delegate(fixture.right_root, fixture_signing_key("right-auth-rotated"), "CHANNEL_AUTH", generation=2)
    rotated_eid = rotated_binding.proof.anchor.eid == rotated_auth.proof.anchor.eid == fixture.right_eid
    assert verify_role(rotated_auth.proof, fixture.right_eid, "CHANNEL_AUTH", 2)
    binding = fixture.initial.binding
    wrong_binding_role = rejects(lambda: sign_binding(binding, fixture.right_auth, 2))
    altered_version = replace(fixture.initial, binding=replace(binding, version=7))
    altered_locator = replace(fixture.initial, binding=replace(binding, locators=frozenset({fixture.new_locator})))
    tampering_detected = rejects(lambda: verify_binding(altered_version, 2)) and rejects(
        lambda: verify_binding(altered_locator, 2)
    )
    fixture.store.records[fixture.right_eid] = altered_locator  # Simulated compromised storage/resolver.
    untrusted_rejected = rejects(lambda: fixture.cache.accept(fixture.store.records[fixture.right_eid], 2))
    fixture.store.records[fixture.right_eid] = fixture.initial
    mismatched_anchor = replace(fixture.right_auth.proof, anchor=fixture.left_auth.proof.anchor)
    wrong_anchor = rejects(lambda: verify_role(mismatched_anchor, fixture.right_eid, "CHANNEL_AUTH", 2))
    wrong_role_proof = AuthenticationProof(
        fixture.right_binding.proof, fixture.right_binding.sign(fixture.transcript.canonical_bytes())
    )
    wrong_channel_role = rejects(
        lambda: verify_establishment(fixture.transcript, fixture.left_proof, wrong_role_proof, 2)
    )
    wrong_channel_eid = rejects(
        lambda: verify_establishment(fixture.transcript, fixture.right_proof, fixture.right_proof, 2)
    )
    transcript_bound = all(
        rejects(partial(verify_establishment, changed, fixture.left_proof, fixture.right_proof, 2))
        for changed in (
            replace(fixture.transcript, left_token=ReceiveToken(b"changed-left")),
            replace(fixture.transcript, right_token=ReceiveToken(b"changed-right")),
            replace(fixture.transcript, left_eid=fixture.right_eid),
            replace(fixture.transcript, right_eid=fixture.left_eid),
        )
    )
    a.channel.queue_message(b"before")
    packet = fixture.send(2)
    bad_data = replace(packet, ciphertext=packet.ciphertext[:-1] + bytes([packet.ciphertext[-1] ^ 1]))
    snapshot = repr(vars(b.channel))
    bad_data_status = fixture.deliver(bad_data, 3)
    unchanged_by_data = snapshot == repr(vars(b.channel))
    assert fixture.deliver(packet, 3, mark=True) == "accepted"
    feedback = b.protect(b.channel.make_feedback())
    bad_control = replace(feedback, ciphertext=feedback.ciphertext[:-1] + bytes([feedback.ciphertext[-1] ^ 1]))
    snapshot = repr(vars(a.channel))
    bad_control_status = a.receive(ProtectedEnvelope(bad_control), 4)
    unchanged_by_control = snapshot == repr(vars(a.channel))
    assert a.receive(ProtectedEnvelope(feedback), 4) == "accepted"
    mark_echo = a.channel.active_path.congestion_marks == 1
    keys_before = (a.incarnation, a._send_key, a._receive_key, b._send_key, b._receive_key)
    fixture.migrate(rotated_binding, 5)
    rollback_rejected = not fixture.cache.accept(fixture.initial, 5)
    a.channel.queue_message(b"after")
    moved_packet = fixture.send(6)
    assert fixture.deliver(moved_packet, 7) == "accepted"
    assert a.receive(ProtectedEnvelope(b.protect(b.channel.make_feedback())), 8) == "accepted"
    crypto_survives = keys_before == (a.incarnation, a._send_key, a._receive_key, b._send_key, b._receive_key)
    raw = scale5_probe()
    raw_criteria = raw["criteria"]
    assert isinstance(raw_criteria, dict)
    return {
        "schema": "netsynth.security-floor.semantic-probe.v1",
        "topology": fixture.graph.to_dict(),
        "parameters": {
            "seed": None,
            "generator": "hand-built-five-node-chain",
            "deterministic_test_secrets": True,
            "signature": "Ed25519",
            "agreement_placeholder": "X25519",
            "kdf": "HKDF-SHA256",
            "aead": "AESGCM",
            "handshake": "complete mutual transcript witness; NOT a new wire/AKE protocol",
            "maximum_message_size": 16,
            "binding_versions": [1, 2],
        },
        "results": {
            "data_tampering": bad_data_status,
            "control_tampering": bad_control_status,
            "delivered_messages": [payload.decode() for payload in b.channel.completed.values()],
            "observed_old_path_marks": a.channel.paths[0].congestion_marks,
            "new_path_marks": a.channel.active_path.congestion_marks,
            "transit_security_records": 0,
            "raw_locator_only": raw_criteria["locator_only_traffic"],
        },
        "criteria": {
            "operational_rotation_preserves_self_certifying_eid": rotated_eid
            and IdentityAnchor(fixture.right_root.public_key().public_bytes_raw()).eid == fixture.right_eid,
            "binding_update_requires_role": wrong_binding_role,
            "signed_version_and_locators_tampering_detected": tampering_detected,
            "untrusted_resolver_cannot_forge": untrusted_rejected,
            "known_binding_version_cannot_regress": rollback_rejected,
            "wrong_anchor_hash_rejected": wrong_anchor,
            "channel_wrong_eid_or_role_rejected": wrong_channel_eid and wrong_channel_role,
            "mutual_auth_binds_both_eids_and_tokens": transcript_bound,
            "migration_preserves_channel_crypto_identity": crypto_survives and fixture.a is a,
            "AEAD_before_data_control_state_mutation": bad_data_status == bad_control_status == "authentication_failed"
            and unchanged_by_data
            and unchanged_by_control,
            "mutable_mark_authenticated_echo": mark_echo and unchanged_by_control,
            "no_security_material_in_transit_state": before == fixture.routing_snapshot(),
            "no_global_directory_CA_or_service_names": not hasattr(fixture.cache, "directory")
            and raw_criteria["locator_only_traffic"] is True,
        },
    }
