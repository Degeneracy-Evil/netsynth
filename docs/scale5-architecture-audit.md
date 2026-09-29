# Scale 5 Architecture Audit

> Status: Scale-5 consolidation before minimal semantic validation.

## 1. Scale-5 architecture in one sentence

NetSynth keeps Scale-4 routing topology-dependent, adds a stable opaque Endpoint ID above it, maps each EID through a flat sharded Binding Service to one or more current Structured Locators, and treats all Locator/Route-Program state as replaceable delivery state rather than peer identity.

## 2. Final Scale-5 objects

### Endpoint

A communicating logical object whose lifetime is independent of physical attachment.

### Endpoint ID

Stable, opaque, topology-independent identifier for an Endpoint.

### Endpoint Binding

Versioned EID-to-LocatorSet state.

### Endpoint Binding Service

Flat-key sharded authoritative storage plus resolver/edge caching.

These are the only new first-class Scale-5 architecture objects.

## 3. Not first-class Scale-5 objects

The following are deliberately **not** introduced:

- generic Channel ID;
- global name-independent routing on EIDs;
- permanent forwarding pointer/home agent;
- separate multihoming protocol;
- DNS-style hierarchical endpoint namespace;
- global binding epoch;
- mandatory direct peer mobility updates.

## 4. Scale-5 packet model

For EID-addressed communication:

```text
Destination EID
Selected Destination Locator
Hop Budget
Route / Transit Stack
Payload
```

Locator remains the Scale-4 routing input.

EID protects identity continuity and final local delivery semantics.

## 5. Lifetime hierarchy

```text
Endpoint ID                 long-lived identity
BindingVersion/LocatorSet   mobility/multihoming lifetime
Structured Locator          routing-structure/attachment lifetime
Route Program               route/cache lifetime
STP generation              path-service lifetime
STP internal realization   local routing lifetime
physical link/queue state   fastest
```

A central design goal is preventing faster-changing state from forcing unnecessary changes in slower layers.

## 6. Mobility sequence

Typical make-before-break mobility:

```text
EID -> {L_old}
     -> {L_old, L_new}
     -> {L_new}
```

Existing cached traffic may continue through `L_old` during overlap.

After removal, stale delivery fails closed at the old attachment, fresh resolution obtains `L_new`, and a new Scale-4 Route Program is compiled.

No global routing update is caused solely by Endpoint movement between existing attachment positions.

## 7. Multihoming

Multihoming is simply a Binding with multiple active Locators.

The ingress may choose among them using current route availability/soft metrics.

No extra identity or routing namespace is introduced.

## 8. Global Binding Service semantics

Architecture commitments:

- flat EID keys;
- deterministic sharding to a small authoritative replica group;
- authority independent of current Endpoint location;
- nearby resolver/cache front ends;
- per-EID ordered BindingVersion;
- no globally synchronous cache invalidation;
- stale cache is safe but may temporarily fail;
- explicit fresh lookup after stale evidence;
- resolver infrastructure reachable directly through Scale-4 Locators.

Exact hashing, consensus, replica placement and storage engine are implementation/distributed-systems choices.

## 9. Why stale mappings are safe

Suppose a cache still returns `L_old`.

The packet also contains EID.

An old attachment may either:
- still host that EID and deliver correctly;
- no longer host it and fail.

It must never reinterpret the EID as another Endpoint.

Therefore stale mapping state can reduce liveness but does not silently change identity.

This property is what permits loose cache consistency.

## 10. Prior-art position

Scale 5 is deliberately a synthesis of established ideas:

- HIP: stable identity and locator changes;
- LISP: EID/RLOC mapping and edge cache;
- ILNP: identifier/locator separation;
- MobilityFirst: flat GUIDs and high-update global resolution;
- DMap/Auspice: sharding and dynamic replication;
- QUIC/MPTCP/SCTP: associations surviving path/address changes.

NetSynth does not claim these primitives as novel.

The architecture-specific composition is that they sit above the frozen Scope/STP/Route-Program substrate and exploit EID-preserving final delivery to tolerate stale binding caches without global synchronization.

## 11. Graceful degeneration

### Locator-only infrastructure traffic

No EID or Binding lookup is required.

### Static Endpoint

Resolve once; binding may remain cached for a long period.

### Mobile Endpoint

Only Binding state changes when it moves between existing Locators.

### Multihomed Endpoint

Binding contains several Locators.

The Scale-4 routing architecture itself is unchanged in all cases.

## 12. Known unresolved issues

Deliberately deferred:

- authentication of EID ownership and binding publication;
- privacy/linkability of stable EIDs;
- exact EID width/cryptographic construction;
- human/service naming;
- source identity;
- transport reliability/order/congestion;
- fast direct peer mobility signaling;
- binding-authority consensus/replica algorithm;
- Scope structural relocation/renumbering.

These are separate future architecture questions.

## 13. Minimal semantic validation required

The Scale-5 prototype should validate only:

1. EID remains unchanged while LocatorSet changes;
2. one EID can hold multiple simultaneous Locators;
3. movement does not alter Scale-4 Scope/pathlet state when attachment positions already exist;
4. stale binding routes to the old Locator but cannot deliver to another Endpoint;
5. stale final-delivery failure triggers fresh binding lookup and a new Route Program;
6. per-EID BindingVersion prevents older resolver state from overwriting newer state;
7. resolver caches may be stale without global invalidation;
8. resolver infrastructure is addressed by Locator and has no recursive EID-resolution dependency;
9. ongoing mock upper-layer state keyed by EID survives a Locator change with no generic Channel object;
10. Locator-only Scale-4 traffic remains possible without Scale-5 machinery.

Do not benchmark DHT algorithms, DNS, LISP, or GNRS performance.

## 14. Freeze criterion

If the minimal prototype verifies these semantics without introducing hidden EID state into transit routing or requiring a generic Channel, freeze Scale 5.

Then return to first principles for the next problem rather than extending mobility mechanisms further.
