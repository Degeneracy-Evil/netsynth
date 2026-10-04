# Security Floor: Endpoint, Binding, and Channel Authentication

> Status: architecture choice after security reconciliation.
>
> This document adds the minimum cryptographic semantics needed to make frozen Scale-5/6 ownership claims meaningful.

## 1. Architecture choice: self-certifying EID anchor

NetSynth defines an immutable **Identity Anchor**.

Conceptually:

~~~text
IdentityAnchor {
    format/version
    root verification public key
    algorithm identifier / agility information
}
~~~

The Endpoint ID is derived from the canonical Anchor representation:

~~~text
EID = Hash(canonical IdentityAnchor)
~~~

The exact hash algorithm and bit width are not frozen here.

This gives a verifier two independent checks:

1. the presented Anchor hashes to the claimed EID;
2. signatures/delegations rooted in that Anchor are valid.

No global registration authority is required merely to establish cryptographic control of an EID.

## 2. Why not hash the current online key directly

HIP's HIT demonstrates the power of a public-key-derived self-certifying identifier, but direct coupling of identity to one operational key makes routine key replacement awkward.

NetSynth instead separates:

~~~text
long-lived Identity Anchor
        !=
online operational keys
~~~

The Anchor normally stays offline or rarely used.

It delegates narrower roles to online keys.

## 3. Role-scoped operational credentials

An Identity Anchor may authorize one or more operational public keys for explicit roles.

The minimum roles are:

~~~text
BINDING_UPDATE
CHANNEL_AUTH
~~~

A credential conceptually binds:

~~~text
EID
role
operational public key
credential generation / validity
delegation constraints
signature by an authorized parent/root key
~~~

The exact certificate format is not frozen.

This adopts the SPKI-style idea that authorization should be attached directly to keys rather than inferred through a global human-readable name hierarchy.

## 4. Routine key rotation

Routine operational-key rotation does not change the EID.

Example:

~~~text
Identity Anchor
    |
    +-- CHANNEL_AUTH key A
    |
    +-- later CHANNEL_AUTH key B
~~~

Peers accept B when presented with a valid authorization chain rooted in the same Identity Anchor.

The same applies to Binding-update keys.

Compromise/recovery of the **Identity Anchor itself** is not solved by ordinary operational-key rotation.

A future production design may precommit recovery/threshold keys or another root-recovery mechanism in the Anchor. The current architecture does not create a mutable external registry solely to recover a compromised root.

## 5. Binding publication becomes signed object state

The Scale-5 authoritative binding is refined to an independently verifiable **Signed Binding Record**.

Conceptually:

~~~text
SignedBinding {
    EID
    BindingVersion
    LocatorSet
    optional expiry/freshness metadata
    signer credential/reference
    signature
}
~~~

The signer must possess an active `BINDING_UPDATE` authorization for that EID.

## 6. Binding Service trust is reduced

The Binding Service still provides:

- sharding;
- storage;
- cache/lookup;
- per-EID monotonic update ordering;
- availability.

But it is no longer trusted to invent binding contents.

Both authoritative storage and clients/resolvers can verify:

~~~text
EID anchor
    -> authorized Binding key
    -> SignedBinding signature
~~~

A compromised resolver/storage node may:
- withhold records;
- replay still-acceptable old records;
- deny service.

It must not be able to forge a new valid LocatorSet for an EID.

This is a meaningful reduction in the Binding Service trust boundary.

## 7. Staleness versus forgery remains separate

Cryptographic signatures do not solve mapping freshness by themselves.

A previously valid signed binding can be replayed.

NetSynth keeps the Scale-5 semantics:

- per-EID BindingVersion prevents rollback when a newer version is already known;
- normal caches may be stale;
- fresh resolution is used after stale-delivery evidence;
- optional signed validity/expiry can bound passive replay.

A brand-new client may temporarily accept an older still-valid signed record.

A malicious authoritative storage quorum can always cause denial or stale service unless stronger consistency/transparency machinery is added.

The security floor does not pretend otherwise.

## 8. Channel establishment uses authenticated key exchange

Scale-6 OPEN/ACCEPT is upgraded from token exchange to a standard **mutually authenticated key exchange**.

NetSynth does not define new Diffie-Hellman/signature/cipher primitives.

A suitable TLS-1.3/Noise-like AKE must establish:

- mutual proof of control of current `CHANNEL_AUTH` credentials;
- ephemeral shared key material with forward-secrecy properties appropriate to the selected AKE;
- a transcript binding both claimed EIDs;
- a transcript binding both Receive Tokens;
- negotiation/version binding sufficient to prevent downgrade/misbinding.

The handshake must not bind Channel identity to Locator or Route Program.

That would break mobility.

## 9. Channel authentication statement

After successful establishment, each side should be able to state:

> The remote peer proved possession of a CHANNEL_AUTH key currently authorized by the Identity Anchor whose hash is the Remote EID, and this proof is bound to this Channel's handshake transcript and Receive Tokens.

This is the exact security meaning needed by Scale 6.

It is not a claim about a human/service name.

## 10. AEAD replaces the prototype checksum

Once a Channel is established, Channel control and Message data are protected with authenticated encryption.

The Scale-6 CRC32 prototype is no longer the production security primitive.

AEAD authenticates at least:

- Receive Token / Channel demux context;
- Packet Number;
- Channel control frames;
- Message fragments;
- ACK / flow-credit state;
- protocol version/context needed to prevent cross-protocol confusion.

Whether some fields are encrypted or authenticated-only is a wire-format decision.

## 11. Confidentiality choice

Although confidentiality was not required to derive routing/reliability semantics, NetSynth chooses encrypted Channel payload/control as the default.

Reason:

- authenticated key exchange already derives symmetric keys;
- transit routers have no legitimate need to inspect Channel internals;
- authenticated encryption is simpler than designing separate integrity-only and confidentiality modes.

Raw Scale-5 best-effort packets may still exist without a Channel and are not automatically confidential.

## 12. Congestion Mark remains outside immutable AEAD state

The Scale-6 Congestion Mark is intentionally mutable by transit forwarding nodes.

Therefore it cannot be an immutable field inside the end-to-end AEAD-protected Channel payload.

Conceptually:

~~~text
Network envelope:
    Destination EID
    Locator
    Route/Transit Stack
    Hop Budget
    Congestion Mark   <- transit-mutable
    encrypted Channel packet
~~~

The receiver echoes observed congestion in an **authenticated Channel ACK**.

An on-path attacker can falsely set congestion marks and reduce throughput, but an on-path attacker can also drop packets entirely. The security floor treats this as availability/DoS, not an identity/integrity failure.

A transit node must never need Channel keys.

## 13. Replay domains

Binding and Channel replay are separate.

### Binding

BindingVersion / freshness semantics reject known rollback and bound cache staleness.

### Channel

The authenticated Channel transcript, Receive Tokens, Packet Number spaces and Channel incarnation prevent an old protected packet from being accepted as fresh state in an unrelated Channel.

Exact crash/restart token/incarnation retention remains part of the previously deferred finite-history design.

## 14. Source identity exposure

Scale 5 did not require Source EID in every network packet.

That remains unchanged.

A Channel handshake communicates/authenticates peer EIDs end to end.

After establishment, transit routing need not learn the sender's stable EID merely because Channel security exists.

Exact privacy/linkability of Destination EID and Receive Tokens is deferred.

## 15. Control-plane routing security is not pulled in here

This security floor does not yet make Byzantine Scope controllers/pathlet advertisers safe.

If the Scale-4 control plane is malicious, it may misroute/drop traffic.

End-to-end Channel AEAD still protects Endpoint payload authenticity/confidentiality against such forwarding participants, but it cannot restore availability.

Authenticating BTG/STP control objects can later use similar signed-role concepts if adversarial routing infrastructure becomes an explicit architecture requirement.

Do not expand the present work into a routing PKI.

## 16. Resulting trust chain

Conceptually:

~~~text
Identity Anchor
      |
      +---- hash ----> Endpoint ID
      |
      +---- delegate ----> Binding Update Key
      |                        |
      |                        +---- sign ----> EID -> LocatorSet
      |
      +---- delegate ----> Channel Auth Key
                               |
                               +---- authenticated AKE
                                          |
                                          +----> Channel AEAD keys
~~~

This is the entire security floor.

## 17. What is deliberately not solved

- human-readable names;
- CA/web PKI;
- service authorization;
- root-anchor compromise recovery;
- anonymity / unlinkability;
- secure routing-control consensus;
- Byzantine Binding-Service availability;
- group identity;
- hardware roots of trust;
- key-storage implementation;
- post-quantum algorithm selection.

These may matter later, but none is required to make the current EID/Binding/Channel semantics internally coherent.

## 18. Minimal semantic validation

A future tiny prototype should test:

1. two operational keys can be delegated under one Anchor without changing EID;
2. a key lacking `BINDING_UPDATE` cannot publish a binding;
3. tampering with a signed LocatorSet/BindingVersion is detected;
4. resolver/storage cannot forge a valid binding;
5. a fresh authorized Binding key can replace an older authorized key while preserving EID;
6. Channel establishment rejects a credential for the wrong EID;
7. successful mutual AKE binds both EIDs and both Receive Tokens;
8. changing Locator/Route Program after establishment does not change Channel cryptographic identity;
9. protected Channel control/data tampering is rejected before state mutation;
10. transit Congestion Mark may be set without invalidating Channel AEAD and is authenticated only when echoed by the peer;
11. transit routing still receives no Channel/identity private keys;
12. service/human names are absent from the security model.

Do not benchmark cryptographic algorithms or invent a new AKE.
