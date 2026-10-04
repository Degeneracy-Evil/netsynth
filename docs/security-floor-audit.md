# Security Floor Architecture Audit

> Status: consolidation before minimal semantic validation.
>
> Decision: NetSynth needs a **minimal security floor**, but security is not promoted to a new architectural Scale.

## 1. Why this work is necessary

Without cryptographic verification:

- anyone could claim an arbitrary Endpoint ID;
- anyone could publish a new LocatorSet for another Endpoint;
- a Channel peer could not know whether the remote party controls the claimed EID;
- the Scale-6 checksum would detect accidents but not attackers.

Those failures invalidate existing Scale-5/6 semantics rather than merely reducing optional security.

Therefore a small trust/authentication layer is required.

## 2. Why this work must remain small

The current architecture does **not** require NetSynth to solve:

- human identity;
- service naming;
- global PKI governance;
- authorization policy;
- anonymity;
- Byzantine routing;
- secure storage;
- hardware trust;
- group key management.

Expanding into those areas now would be a direction error.

## 3. Frozen security-floor choices

### Self-certifying EID

~~~text
EID = Hash(canonical Identity Anchor)
~~~

The Anchor is long-lived and carries the root verification material / agility context.

### Delegated operational keys

The Anchor delegates explicit roles:

~~~text
BINDING_UPDATE
CHANNEL_AUTH
~~~

Routine operational-key rotation does not change EID.

### Self-contained proof

The party making a security-sensitive claim supplies enough Anchor/delegation material for the verifier to recompute the EID and verify the role.

No global public-key lookup service is introduced.

### Signed bindings

Binding publication is an independently verifiable signed object.

The Binding Service remains responsible for storage/order/availability, but not for inventing authentic LocatorSet contents.

### Authenticated Channel establishment

OPEN/ACCEPT becomes a standard mutually authenticated ephemeral AKE.

The transcript binds:
- both EIDs;
- both Receive Tokens;
- protocol/negotiation context.

It deliberately does not bind Locator or Route Program.

### AEAD Channel

Established Channel control/data is encrypted and authenticated end to end.

### Mutable network congestion signal

Congestion Mark remains outside immutable Channel AEAD and is echoed in authenticated feedback.

## 4. Important trust distinction

The self-certifying EID proves:

> "This actor controls credentials authorized under Endpoint ID X."

It does not prove:

> "Endpoint X is Alice / example.com / a trusted service."

That mapping is a later naming/policy question.

## 5. Key-lifetime hierarchy

~~~text
EID / Identity Anchor        very long-lived
operational role credential  rotatable
Channel ephemeral keys       per Channel / key epoch
Binding signature            per binding update
AEAD traffic keys            Channel key lifetime
~~~

This continues the NetSynth principle that faster-changing material should not force slower identity changes.

## 6. Root compromise caveat

If the immutable Identity Anchor's root authority is compromised, ordinary role-key rotation cannot restore trust.

Possible production solutions include:
- precommitted recovery keys;
- threshold root authority;
- explicit anchor succession mechanisms.

NetSynth deliberately does not design one yet.

This is preferable to introducing an external mutable global identity registry before a real requirement forces it.

## 7. Binding replay caveat

Signatures prevent forgery, not indefinite withholding/replay.

Per-EID BindingVersion and known-version caches prevent rollback once newer state is known.

A first-time verifier may accept an older still-valid signed Binding.

A malicious storage authority can always cause stale service or denial unless stronger transparency/consistency machinery is added.

This limitation is explicit and acceptable at the current security floor.

## 8. Routing-control threat boundary

Scale-4 Scope/STP control remains non-Byzantine in the current model.

A malicious router/controller may cause denial or misrouting.

End-to-end Channel AEAD protects payload confidentiality/authenticity but cannot guarantee availability.

Do not introduce a routing PKI merely because Endpoint authentication now exists.

## 9. Compatibility with frozen architecture

Security does not add:
- routing lookup state in transit routers;
- a new address namespace;
- a Channel routing identity;
- a global CA namespace;
- a new mapping layer.

It authenticates existing objects.

## 10. Minimal semantic validation criteria

A tiny prototype should demonstrate:

1. EID is deterministically derived from an Identity Anchor;
2. rotating BINDING_UPDATE / CHANNEL_AUTH operational keys preserves EID;
3. a role-inappropriate key cannot authorize a Binding update;
4. modified signed binding contents fail verification;
5. forged resolver/storage contents fail independent client verification;
6. lower BindingVersion cannot replace known newer state;
7. Channel establishment fails for an Anchor/credential not matching the claimed EID;
8. successful mutual AKE binds both EIDs and Receive Tokens;
9. Locator / Route Program replacement leaves Channel cryptographic identity and traffic keys semantically attached to the same EID Channel;
10. protected Channel data/control tampering fails before transport-state mutation;
11. transit Congestion Mark can change without breaking endpoint AEAD and the peer's echo is authenticated;
12. no private key or operational role credential appears in transit routing state;
13. no human/service-name trust is needed.

Do not benchmark cryptography, certificate formats or AKE implementations.

## 11. Freeze criterion

If these semantics work, freeze the Security Floor.

Then resume the architecture's scale-by-scale first-principles progression rather than extending security features.
