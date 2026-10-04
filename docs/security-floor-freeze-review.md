# Security Floor Freeze Review

> Reviewed implementation: `acc690e96cd17de82df1877b8c084be0fd186b4a`.
>
> Decision: **the NetSynth Security Floor is frozen.**
>
> This is a cross-cutting minimum trust layer, not a new architectural Scale and not a general security subsystem.

## 1. Review result

The prototype preserves the intended boundary.

It adds only endpoint/object-validation semantics around already frozen Scale-5/6 objects:

- self-certifying Endpoint identity;
- role-scoped operational delegation;
- signed Binding records;
- mutually authenticated Channel transcript semantics;
- endpoint AEAD;
- authenticated echo of the transit-mutable congestion signal.

Scale-4/5/6 routing, identity and transport source semantics remain unchanged.

No global CA, human/service naming hierarchy, routing PKI, or identity-directory service was introduced.

## 2. Freeze criteria

All thirteen criteria from `docs/security-floor-audit.md` are represented by direct implementation checks/tests.

### Self-certifying EID

The Identity Anchor has a canonical public representation and:

~~~text
EID = SHA-256(canonical Anchor)
~~~

A verifier receives the Anchor in the proof bundle and recomputes the claimed EID locally.

No separate EID-to-public-key directory is needed.

### Operational-key rotation preserves identity

Different `BINDING_UPDATE` or `CHANNEL_AUTH` operational keys can be delegated by the same immutable Anchor.

Changing those online keys does not change EID.

### Role separation is enforced

A CHANNEL_AUTH credential cannot sign an accepted Binding merely because its cryptographic signature is otherwise valid.

A BINDING_UPDATE credential cannot substitute for Channel authentication.

Role is part of the root-signed delegation statement.

### Signed Binding integrity

Binding EID, BindingVersion, LocatorSet and cache lifetime are all covered by the operational signature.

Modification of any covered field fails independent verification.

### Binding storage is not trusted for authenticity

A new verifier needs only:
- SignedBinding;
- embedded public Identity Anchor/delegation proof.

The storage/resolver may return malicious content, but it cannot forge an accepted Binding without an authorized key.

Known-version state continues to reject rollback/conflicting equal versions.

### Wrong Anchor / claimed EID is rejected

Replacing the Anchor or claiming another EID breaks the self-certifying check before delegated-role proof is accepted.

### Channel role / EID authentication

A complete signed establishment transcript binds:
- both Endpoint IDs;
- both Receive Tokens;
- both ephemeral DH public keys;
- resource agreement;
- protocol/algorithm context.

Credential for the wrong EID or wrong role fails verification.

### Ephemeral possession is required

The semantic AKE witness verifies that supplied private X25519 values correspond to the authenticated ephemeral public keys.

The prototype deliberately does not pretend this single function is a production handshake protocol.

### Channel security survives path migration

Locator, Binding and Route Program changes leave:
- Channel identity;
- transcript incarnation;
- directional traffic keys;
- Receive Tokens

unchanged.

No cryptographic identity is tied to Locator or Route Program.

### AEAD gates Channel mutation

Protected Channel frames are decrypted/authenticated before frozen Scale-6 parsing or state mutation.

Tampering with:
- data;
- control;
- token;
- Packet Number;
- channel incarnation/direction

fails authentication without mutating Channel state.

The old CRC remains only an internal semantic compatibility check after AEAD.

### Mutable Congestion Mark remains possible

The network congestion mark is outside immutable Channel AEAD.

Transit can monotonically set it without keys.

The receiver records the observation and sends congestion feedback inside authenticated Channel control state.

An attacker may falsely mark/drop traffic and cause denial/performance degradation, but cannot forge protected Endpoint data/control.

### No security secrets in routing state

Routing snapshots remain unchanged.

Scope, Route Service, STP and Route Program objects contain no:
- private keys;
- traffic keys;
- operational credentials;
- Identity Anchors required for forwarding.

Transit forwarding does not become identity-aware security state.

### No human/service naming trust is introduced

The model verifies cryptographic control of an EID only.

It makes no claim that an EID corresponds to a human, DNS/service name, organization, or trusted application.

## 3. Important deliberately weak semantics

### Credential generation is not revocation

Issuing generation 2 does not automatically invalidate generation 1.

Generation identifies/version-tags credentials; validity intervals currently decide whether a credential is acceptable.

Immediate revocation would require an additional freshness/revocation mechanism and is **not** part of the frozen floor.

### No global trusted-clock architecture is frozen

The semantic prototype receives a `now` value to exercise credential validity intervals.

NetSynth does not currently define:
- synchronized global clocks;
- secure time distribution;
- allowed clock skew.

Clock disagreement can cause availability failures. It must not be silently turned into a future global-time dependency.

A production credential model may choose short-lived credentials, explicit epochs, revocation objects, or another established mechanism if a later requirement forces it.

### First-contact Binding freshness remains unsolved

A valid signature proves authenticity, not newest state.

A first-contact client may accept an older authentic Binding that is still acceptable under the freshness policy.

This was already true in Scale 5 and is intentionally not hidden by cryptography.

### Root compromise is outside routine rotation

Compromise of the immutable Identity Anchor cannot be repaired merely by rotating an operational key.

Precommitted recovery/threshold/succession is a later problem if required.

## 4. Cryptographic implementation status

The semantic prototype uses established library primitives:

- Ed25519;
- X25519;
- HKDF-SHA256;
- AES-GCM.

These are **prototype selections**, not NetSynth's frozen cipher suite.

The architecture freezes only:

- self-certifying Anchor-derived EID;
- role-authorized public verification;
- authenticated ephemeral key establishment;
- directional authenticated-encryption keys.

A production implementation should use a reviewed standard AKE/protocol construction rather than reproducing `establish_protected_channel()` as a wire handshake.

## 5. Dependency note

The semantic prototype adds the `cryptography` package.

That dependency exists to avoid inventing fake signature/DH/AEAD primitives for validation.

It should not be interpreted as a requirement that every future NetSynth simulator/routing-only tool must always load cryptography; dependency factoring may be revisited during repository cleanup without changing the architecture.

## 6. Frozen trust chain

Conceptually:

~~~text
Identity Anchor
      |
      +---- hash ----> Endpoint ID
      |
      +---- signed delegation ----> BINDING_UPDATE key
      |                                |
      |                                +---- sign ----> Binding
      |
      +---- signed delegation ----> CHANNEL_AUTH key
                                       |
                                       +---- authenticated AKE
                                                  |
                                                  +---- Channel traffic keys
                                                               |
                                                               +---- AEAD Channel
~~~

That is the entire Security Floor.

## 7. Freeze boundary

Do not extend this floor by default into:

- Web-style/global CA PKI;
- human/service identity;
- authorization policy systems;
- general capability frameworks;
- revocation/transparency infrastructure;
- Byzantine routing security;
- anonymity/privacy systems;
- hardware attestation;
- group communication security;
- custom cryptographic algorithms/protocols.

Only reopen a security question when a later architecture requirement cannot be expressed safely with the frozen floor.

## 8. Return to architecture derivation

Security work stops here.

The project should resume the original scale-by-scale architecture process:

~~~text
architecture question
    -> theory/prior-art reconciliation
    -> explicit NetSynth choice
    -> minimal validation
~~~

The next question should be selected from the next communication/network requirement forced by the architecture, not from a desire to add more security features.
