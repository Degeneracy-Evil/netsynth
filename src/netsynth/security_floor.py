"""Security-floor semantic witnesses, NOT a new AKE protocol or certificate format."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from hashlib import sha256
from typing import Literal, cast

from cryptography.exceptions import InvalidSignature, InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from netsynth.scale5 import EndpointBinding, EndpointID
from netsynth.scale6 import Channel, ChannelPacket, Feedback, Fragment, Frame, ReceiveToken

type Role = Literal["BINDING_UPDATE", "CHANNEL_AUTH"]
ANCHOR_CONTEXT = "netsynth-identity-anchor-semantic-v1/Ed25519-SHA256"
BINDING_CONTEXT = "netsynth-signed-binding-semantic-v1/Ed25519"
CONTEXT = "netsynth-security-floor-semantic-v1/Ed25519-X25519-HKDF-SHA256-AESGCM"


def canonical(domain: str, *values: object) -> bytes:
    """Deterministic fixture encoding with operation separation, not a production format."""
    return json.dumps([domain, *values], separators=(",", ":"), sort_keys=True).encode()


@dataclass(frozen=True)
class IdentityAnchor:
    root_public_key: bytes
    version: int = 1
    algorithm_context: str = ANCHOR_CONTEXT

    def canonical_bytes(self) -> bytes:
        return canonical("anchor", self.version, self.algorithm_context, self.root_public_key.hex())

    @property
    def eid(self) -> EndpointID:
        return EndpointID(sha256(self.canonical_bytes()).digest())


@dataclass(frozen=True)
class RoleCredential:
    eid: EndpointID
    role: Role
    public_key: bytes
    generation: int
    not_before: int
    not_after: int
    root_signature: bytes

    def statement(self) -> bytes:
        return canonical(
            "delegation",
            self.eid.value.hex(),
            self.role,
            self.public_key.hex(),
            self.generation,
            self.not_before,
            self.not_after,
        )


@dataclass(frozen=True)
class IdentityProofBundle:
    anchor: IdentityAnchor
    credential: RoleCredential


@dataclass(frozen=True)
class OperationalSigner:
    proof: IdentityProofBundle
    private_key: Ed25519PrivateKey = field(repr=False, compare=False)

    def sign(self, statement: bytes) -> bytes:
        if self.private_key.public_key().public_bytes_raw() != self.proof.credential.public_key:
            raise ValueError("operational private key does not match delegated public key")
        return self.private_key.sign(statement)


def delegate(
    root: Ed25519PrivateKey,
    operational: Ed25519PrivateKey,
    role: Role,
    generation: int = 1,
    not_before: int = 0,
    not_after: int = 100,
) -> OperationalSigner:
    anchor = IdentityAnchor(root.public_key().public_bytes_raw())
    unsigned = RoleCredential(
        anchor.eid, role, operational.public_key().public_bytes_raw(), generation, not_before, not_after, b""
    )
    credential = RoleCredential(
        unsigned.eid, role, unsigned.public_key, generation, not_before, not_after, root.sign(unsigned.statement())
    )
    return OperationalSigner(IdentityProofBundle(anchor, credential), operational)


def verify_role(proof: IdentityProofBundle, eid: EndpointID, role: Role, now: int) -> Ed25519PublicKey:
    """Public-only verification: no identity directory or verifier-held signing secret."""
    anchor, credential = proof.anchor, proof.credential
    if anchor.version != 1 or anchor.algorithm_context != ANCHOR_CONTEXT or anchor.eid != eid or credential.eid != eid:
        raise ValueError("Anchor does not match claimed EID or supported context")
    if credential.role != role or credential.generation < 1 or not credential.not_before <= now < credential.not_after:
        raise ValueError("wrong role or inactive credential")
    try:
        Ed25519PublicKey.from_public_bytes(anchor.root_public_key).verify(
            credential.root_signature, credential.statement()
        )
        return Ed25519PublicKey.from_public_bytes(credential.public_key)
    except (InvalidSignature, ValueError) as error:
        raise ValueError("invalid delegation") from error


def binding_statement(binding: EndpointBinding) -> bytes:
    return canonical(
        "signed-binding",
        BINDING_CONTEXT,
        binding.eid.value.hex(),
        binding.version,
        [[list(locator.components), locator.selector] for locator in sorted(binding.locators)],
        binding.cache_lifetime,
    )


@dataclass(frozen=True)
class SignedBinding:
    binding: EndpointBinding
    proof: IdentityProofBundle
    signature: bytes


def sign_binding(binding: EndpointBinding, signer: OperationalSigner, now: int) -> SignedBinding:
    verify_role(signer.proof, binding.eid, "BINDING_UPDATE", now)
    return SignedBinding(binding, signer.proof, signer.sign(binding_statement(binding)))


def verify_binding(record: SignedBinding, now: int) -> EndpointBinding:
    public_key = verify_role(record.proof, record.binding.eid, "BINDING_UPDATE", now)
    try:
        public_key.verify(record.signature, binding_statement(record.binding))
    except InvalidSignature as error:
        raise ValueError("forged or modified Binding") from error
    return record.binding


class VerifiedBindingCache:
    """Independent signature/known-version gate even if the storage is malicious."""

    def __init__(self) -> None:
        self.bindings: dict[EndpointID, EndpointBinding] = {}

    def accept(self, record: SignedBinding, now: int) -> bool:
        binding = verify_binding(record, now)
        previous = self.bindings.get(binding.eid)
        if previous is not None:
            if binding.version < previous.version:
                return False
            if binding.version == previous.version:
                if binding != previous:
                    raise ValueError("conflicting signed BindingVersion")
                return False
        self.bindings[binding.eid] = binding
        return True


class SignedBindingStore:
    """Tiny signed-object storage/publication model; public records can be adversarially replaced."""

    def __init__(self) -> None:
        self.records: dict[EndpointID, SignedBinding] = {}
        self._publication_gate = VerifiedBindingCache()

    def publish(self, record: SignedBinding, now: int) -> bool:
        if not self._publication_gate.accept(record, now):
            return False
        self.records[record.binding.eid] = record
        return True


@dataclass(frozen=True)
class EstablishmentTranscript:
    left_eid: EndpointID
    right_eid: EndpointID
    left_token: ReceiveToken
    right_token: ReceiveToken
    left_ephemeral: bytes
    right_ephemeral: bytes
    maximum_message_size: int
    left_capacity: int
    right_capacity: int
    context: str = CONTEXT

    def canonical_bytes(self) -> bytes:
        return canonical(
            "mutual-channel-establishment",
            self.context,
            self.left_eid.value.hex(),
            self.right_eid.value.hex(),
            self.left_token.value.hex(),
            self.right_token.value.hex(),
            self.left_ephemeral.hex(),
            self.right_ephemeral.hex(),
            self.maximum_message_size,
            self.left_capacity,
            self.right_capacity,
        )

    @property
    def incarnation(self) -> bytes:
        return sha256(self.canonical_bytes()).digest()


@dataclass(frozen=True)
class AuthenticationProof:
    bundle: IdentityProofBundle
    signature: bytes


def authenticate_transcript(
    transcript: EstablishmentTranscript, signer: OperationalSigner, now: int
) -> AuthenticationProof:
    verify_role(signer.proof, signer.proof.anchor.eid, "CHANNEL_AUTH", now)
    return AuthenticationProof(signer.proof, signer.sign(transcript.canonical_bytes()))


def verify_establishment(
    transcript: EstablishmentTranscript, left: AuthenticationProof, right: AuthenticationProof, now: int
) -> None:
    """A complete mutually signed transcript witness, not a handshake protocol/state machine."""
    if (
        transcript.context != CONTEXT
        or not transcript.left_token.value
        or not transcript.right_token.value
        or transcript.maximum_message_size < 1
        or min(transcript.left_capacity, transcript.right_capacity) < transcript.maximum_message_size
        or len(transcript.left_ephemeral) != 32
        or len(transcript.right_ephemeral) != 32
    ):
        raise ValueError("invalid establishment context/resource agreement")
    for eid, proof in ((transcript.left_eid, left), (transcript.right_eid, right)):
        key = verify_role(proof.bundle, eid, "CHANNEL_AUTH", now)
        try:
            key.verify(proof.signature, transcript.canonical_bytes())
        except InvalidSignature as error:
            raise ValueError("Channel transcript authentication failed") from error


def _integer(value: object) -> int:
    if type(value) is not int:
        raise ValueError("integer frame field required")
    return value


def _list(value: object) -> list[object]:
    if not isinstance(value, list):
        raise ValueError("list frame field required")
    return cast("list[object]", value)


def encode_frame(frame: Frame) -> bytes:
    if isinstance(frame, Fragment):
        return canonical("fragment", frame.message_id, frame.total_size, frame.offset, frame.payload.hex())
    return canonical("feedback", frame.receipts, frame.credit_limit)


def decode_frame(payload: bytes) -> Frame:
    data = _list(json.loads(payload))
    if len(data) == 5 and data[0] == "fragment" and isinstance(data[4], str):
        return Fragment(_integer(data[1]), _integer(data[2]), _integer(data[3]), bytes.fromhex(data[4]))
    if len(data) == 3 and data[0] == "feedback":
        receipts: list[tuple[int, bool]] = []
        for receipt in _list(data[1]):
            pair = _list(receipt)
            if len(pair) != 2 or type(pair[1]) is not bool:
                raise ValueError("invalid receipt")
            receipts.append((_integer(pair[0]), pair[1]))
        return Feedback(tuple(receipts), _integer(data[2]))
    raise ValueError("unsupported transport frame")


@dataclass(frozen=True)
class ProtectedPacket:
    receive_token: ReceiveToken
    packet_number: int
    ciphertext: bytes


@dataclass(frozen=True)
class ProtectedEnvelope:
    packet: ProtectedPacket
    congestion_mark: bool = False

    def mark_congestion(self) -> ProtectedEnvelope:
        return ProtectedEnvelope(self.packet, True)


class ProtectedChannel:
    """Endpoint-only AEAD gate around frozen Scale-6 state, with no graph/routing access."""

    def __init__(self, channel: Channel, incarnation: bytes, send_key: bytes, receive_key: bytes) -> None:
        self.channel = channel
        self.incarnation = incarnation
        self._send_key, self._receive_key = send_key, receive_key
        self._sealed: dict[int, tuple[bytes, ProtectedPacket]] = {}

    def _aad(self, token: ReceiveToken, number: int) -> bytes:
        return canonical("channel-aead", CONTEXT, self.incarnation.hex(), token.value.hex(), number)

    @staticmethod
    def _nonce(number: int) -> bytes:
        if not 0 <= number < 2**96:
            raise ValueError("prototype nonce space exhausted or invalid; never wrap")
        return number.to_bytes(12)

    def protect(self, packet: ChannelPacket) -> ProtectedPacket:
        if (
            packet.source_eid != self.channel.local_eid
            or packet.destination_eid != self.channel.remote_eid
            or packet.receive_token != self.channel.remote_receive_token
            or packet.checksum != packet.expected_checksum()
            or not 0 <= packet.packet_number < self.channel.next_packet_number
        ):
            raise ValueError("packet does not belong to this sending Channel")
        plaintext = encode_frame(packet.frame)
        previous = self._sealed.get(packet.packet_number)
        if previous is not None:
            if previous[0] != plaintext:
                raise ValueError("Packet Number must never encrypt different content under the same key")
            return previous[1]
        ciphertext = AESGCM(self._send_key).encrypt(
            self._nonce(packet.packet_number), plaintext, self._aad(packet.receive_token, packet.packet_number)
        )
        sealed = ProtectedPacket(packet.receive_token, packet.packet_number, ciphertext)
        self._sealed[packet.packet_number] = (plaintext, sealed)
        return sealed

    def receive(self, envelope: ProtectedEnvelope, now: int) -> str:
        packet = envelope.packet
        try:
            plaintext = AESGCM(self._receive_key).decrypt(
                self._nonce(packet.packet_number),
                packet.ciphertext,
                self._aad(packet.receive_token, packet.packet_number),
            )
            frame = decode_frame(plaintext)
        except InvalidTag, ValueError, UnicodeError:
            return "authentication_failed"
        # Only after endpoint AEAD succeeds do frozen Channel validation/dedup/ACK/credit run.
        transport = ChannelPacket.create(
            self.channel.remote_eid, self.channel.local_eid, packet.receive_token, packet.packet_number, frame
        )
        return self.channel.receive(transport, now, envelope.congestion_mark)


def establish_protected_channel(
    transcript: EstablishmentTranscript,
    left_proof: AuthenticationProof,
    right_proof: AuthenticationProof,
    left_ephemeral: X25519PrivateKey,
    right_ephemeral: X25519PrivateKey,
    now: int,
) -> tuple[ProtectedChannel, ProtectedChannel]:
    """Verify witnesses, then instantiate the already negotiated frozen Channel semantics.

    Existing library primitives supply a local AKE-result placeholder. This function does not
    define OPEN flight ordering, TLS/Noise wire behavior, key confirmation or a new AKE protocol.
    Production must use a standard reviewed AKE; deterministic fixture secrets are test-only.
    """
    verify_establishment(transcript, left_proof, right_proof, now)
    if (
        left_ephemeral.public_key().public_bytes_raw() != transcript.left_ephemeral
        or right_ephemeral.public_key().public_bytes_raw() != transcript.right_ephemeral
    ):
        raise ValueError("ephemeral private key does not match authenticated transcript")
    left_secret = left_ephemeral.exchange(X25519PublicKey.from_public_bytes(transcript.right_ephemeral))
    right_secret = right_ephemeral.exchange(X25519PublicKey.from_public_bytes(transcript.left_ephemeral))

    def derive(secret: bytes) -> bytes:
        return HKDF(algorithm=hashes.SHA256(), length=64, salt=transcript.incarnation, info=CONTEXT.encode()).derive(
            secret
        )

    left_keys, right_keys = derive(left_secret), derive(right_secret)
    a = Channel(
        transcript.left_eid,
        transcript.right_eid,
        transcript.left_token,
        transcript.right_token,
        transcript.maximum_message_size,
        transcript.left_capacity,
        transcript.right_capacity,
    )
    b = Channel(
        transcript.right_eid,
        transcript.left_eid,
        transcript.right_token,
        transcript.left_token,
        transcript.maximum_message_size,
        transcript.right_capacity,
        transcript.left_capacity,
    )
    return (
        ProtectedChannel(a, transcript.incarnation, left_keys[:32], left_keys[32:]),
        ProtectedChannel(b, transcript.incarnation, right_keys[32:], right_keys[:32]),
    )
