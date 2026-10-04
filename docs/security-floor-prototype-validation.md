# Security Floor: tiny semantic validation

## Reconciliation / scope

Mathematical abstraction: self-certifying public-key identities, role-scoped signed authorization,
authenticated object state, and endpoint authenticated-encryption state across path replacement.

Closest established problems: HIP-like self-certifying identity, SPKI-style delegation, signed mapping
objects, and TLS/Noise-style mutually authenticated ephemeral key exchange.

Known constructions / upper bounds: use existing Ed25519, X25519, HKDF-SHA256 and AESGCM primitives.
Their implementations come from `cryptography`; no signature, DH, KDF, cipher or handshake protocol
is invented. Python's standard library alone cannot provide independently public-verifiable signatures
and AEAD; giving a resolver an HMAC verification secret would also give it forgery authority.

Known lower bounds / impossibility: signatures do not prove newest state to a first-contact client;
cryptography does not guarantee availability against dropping/withholding; operational rotation does
not recover a compromised immutable root. These are already documented Security Floor limits.

Why existing results do not fully answer NetSynth: only their composition with frozen EID/Binding/Channel
lifetimes and mutable congestion marking needs validation, not the primitives' security or performance.

NetSynth-specific question: can public-only ownership verification and endpoint AEAD protect existing
objects without a global identity directory, Locator identity coupling or transit security state?

Minimal experiment: reuse the five-node chain, two Anchors, two roles, two binding versions, two
remote attachments and a few Messages; inject credential, record, transcript and ciphertext tampering.

## Implemented boundary

`security_floor.py` adds a frozen Identity Anchor with deterministic canonical encoding and SHA-256 EID.
The Anchor's context describes root verification/hash material, not the online Channel cipher suite.
One-hop root-signed credentials bind EID, role, operational public key, generation and validity interval.
Self-contained bundles carry only public Anchor/delegation material. Verification needs no root secrets,
global public-key lookup, CA, service-name lookup or human identity assertion.

Signed Bindings include EID, version, canonical sorted LocatorSet and cache lifetime. Publication and
client acceptance independently verify the `BINDING_UPDATE` role and object signature. The tiny storage
model deliberately permits adversarial replacement of returned objects; clients do not trust storage.
Known version floors reject rollback and conflicting equal versions. A new client can still accept an
old authentic, currently verifiable record: authenticity and freshness remain different properties.

Channel establishment is a **complete mutually authenticated transcript witness**, not a new wire
handshake or an implementation of TLS/Noise. It checks both `CHANNEL_AUTH` delegations and signatures
over both EIDs, both Receive Tokens, both ephemeral public keys, version/suite context and resource
agreement. X25519/HKDF provide an AKE-result placeholder with independent directional traffic keys.
Both private ephemeral inputs are supplied locally to the semantic witness; production must instead
use a standard reviewed AKE with its real flight ordering, confirmation and replay rules.

The transcript intentionally excludes Locators and Route Programs. Protected Channel wrappers retain
their cryptographic incarnation and keys when the frozen Channel replaces Path State. AEAD encrypts
control/data frames and authenticates token, Packet Number and transcript context before decoding or
calling Scale-6 state mutation. The frozen CRC is only an internal compatibility check after AEAD,
never the protected ingress's security decision.

Directional keys and monotonic Packet Numbers give separate nonce domains. The wrapper rejects
out-of-range numbers and different plaintext under a previously sealed number; exact repeats return
the existing ciphertext. Logical retransmission uses a fresh Packet Number as before.

Congestion Mark remains an outer monotonic soft bit and is deliberately outside AEAD. Its per-PN peer
echo is encrypted/authenticated in feedback. A router needs neither Channel keys nor credentials to mark.
False on-path marks remain an availability/throughput attack, not a payload integrity failure.

## Validation

```bash
uv run --locked python src/security_floor_main.py
uv run --locked python scripts/check.py
```

Output schema: `netsynth.security-floor.semantic-probe.v1`. The fixture records topology, primitive
choices, limits and deterministic-test-secret warning, but emits no private or traffic key material.

All thirteen requested criteria pass. Messages `before` and `after` deliver across signed binding
version 1 → 2 and route replacement with the same protected Channel. Tampered data/control return
`authentication_failed` without transport mutation. Marks are echoed to the sending path; the new path
has no inherited marks. Routing snapshots remain unchanged and Locator-only traffic still works.

Additional direct tests cover credential/validity tampering, wrong-role signatures even when the object
signature is cryptographically correct, independent first-contact verification, equal-version conflict,
complete transcript substitution, wrong ephemeral possession, cross-direction/incarnation replay,
nonce-reuse refusal, retransmission, duplicate suppression and authenticated congestion feedback.

Scale-4/5/6 source files are unchanged. Security is an endpoint/object-validation layer, not a generic
framework, Channel routing identity, routing PKI, new authority-sharding algorithm or naming service.

## Remaining limits / ambiguities

- All fixture secrets are deterministic and publicly reproducible: never deploy them. Algorithm choice,
  canonical JSON and the Anchor/certificate fields are prototype choices, not a production format.
- Root-only delegation suffices here; no general delegation framework, revocation directory, root
  succession/recovery, application policy or service-name trust was necessary.
- Generation identifies a credential; issuing generation 2 does **not** silently revoke generation 1.
  Current validity intervals are checked locally. Immediate revocation, trusted clock policy and Anchor
  compromise recovery remain explicit future decisions rather than hidden global dependencies.
- Signed-object gates do not replace frozen resolver caching/availability semantics or implement a
  distributed service. Malicious storage can still replay first-contact authentic state or deny service.
- Real AKE replay/liveness/confirmation, key epochs/rekey, crash/restart and bounded history reclamation
  are unimplemented. Fresh per-Channel tokens/ephemeral material are a fixture assumption; unrelated
  Channel incarnations have different derived keys. This is semantic evidence, not a security proof.
- AEAD frame encoding and fixed historical PMTU accounting are not real encrypted wire packetization.
  Ciphertext/tag/control overhead must be accounted in a future wire model, not silently folded into
  frozen Scale-6 semantics here.
- Byzantine Scope/STP control and availability guarantees remain outside the floor. No unnecessary
  global CA, identity directory or routing-security mechanism was introduced.

Primitive references: [Ed25519](https://cryptography.io/en/latest/hazmat/primitives/asymmetric/ed25519/),
[X25519](https://cryptography.io/en/latest/hazmat/primitives/asymmetric/x25519/),
[HKDF](https://cryptography.io/en/latest/hazmat/primitives/key-derivation-functions/),
[AEAD](https://cryptography.io/en/latest/hazmat/primitives/aead/).
