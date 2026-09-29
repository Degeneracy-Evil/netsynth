# Scale 5: Stable Endpoint Identity and Mobility

> Status: architecture choice after theory reconciliation.
>
> Scale 4 is frozen. Scale 5 introduces only the machinery forced by one new requirement:
>
> A communicating entity may change its forwarding attachment while existing and future communication should still refer to the same entity.

## 1. What breaks in Scale 4

Scale 4 addresses a destination by a topology-dependent Structured Locator.

That is correct for routing, but it also means that moving the destination to another attachment changes the Locator.

Three possible responses exist:

1. change every reference to the destination;
2. keep the old Locator stable and insert forwarding indirection from the old location;
3. introduce a stable identity above the Locator and resolve it to current attachment Locators.

NetSynth chooses the third.

This is an architecture choice, not a theorem that identifier/locator separation is mandatory.

## 2. Theory and prior-architecture reconciliation

### HIP

HIP separates a stable Host Identity from IP locators. Transport associations bind to the identity, and peers can update Locator Sets as attachments change. Rendezvous infrastructure is used when direct peer-to-peer readdressing is insufficient, including initial reachability and simultaneous movement.

### LISP

LISP separates EIDs from RLOCs and uses a Mapping System. Ingress routers resolve and cache EID-to-RLOC mappings on demand; mapping changes refresh cached state.

### ILNP

ILNP separates Identifier and Locator semantics and treats mobility and multihoming as changes in Locator values, with dynamic naming/rendezvous support.

### MobilityFirst

MobilityFirst explicitly uses stable GUIDs plus a Global Name Resolution Service mapping them to one or more current network addresses.

### Name-independent compact routing

General weighted graphs can route directly on arbitrary stable names with sublinear local state and bounded stretch. Therefore explicit resolution is not mathematically required.

NetSynth nevertheless keeps stable-name resolution outside Scale-4 routing because the frozen Scale-4 architecture deliberately routes on topology-dependent Locators and compiles Route Programs at the edge.

## 3. Architecture choice: Endpoint ID

Scale 5 introduces a topology-independent **Endpoint ID (EID)**.

An Endpoint is a communicating logical object, not necessarily:
- a physical machine;
- a network interface;
- a forwarding node;
- a user identity;
- a security principal.

An Endpoint may migrate between machines or attachments while retaining the same EID.

The EID is:
- opaque;
- topology-independent;
- stable for the lifetime chosen by the Endpoint;
- intended to be globally/statistically unique;
- devoid of routing hierarchy or administrative semantics.

The common architecture should support locally generated high-entropy identifiers. Exact bit width and future cryptographic binding are deferred.

## 4. Locator remains a separate routing primitive

Structured Locator remains exactly what Scale 4 needs: a topology-dependent coordinate for a forwarding position.

At Scale 5 its role becomes sharper:

- EID answers **who/what communication endpoint?**
- Locator answers **where should Scale-4 routing currently deliver?**

Do not make Locator stable by adding hidden home-agent semantics.

A fixed infrastructure/control service may still communicate directly by Locator without using an EID. This also provides a clean bootstrap path for the identity-resolution infrastructure itself.

## 5. Attachment Binding

The Endpoint's current network presence is represented by a binding:

```text
EndpointBinding {
    EndpointID
    BindingGeneration
    LocatorSet
    Lifetime
}
```

where `LocatorSet` contains one or more current Structured Locators.

The binding's hard semantics are:

> packets addressed to this EID may currently be delivered through any active Locator in the set.

Preferences, measured path quality, access-network cost, and similar properties are soft metadata and are not part of identity.

## 6. Mobility and multihoming are the same state transition

### Single attachment

```text
EID -> {L1}
```

### Make-before-break movement

```text
EID -> {L1}
EID -> {L1, L2}
EID -> {L2}
```

### Break-before-make movement

```text
EID -> {L1}
EID -> {}
EID -> {L2}
```

### Multihoming

```text
EID -> {L1, L2, ...}
```

No separate architectural primitive is required for multihoming.

## 7. Architecture choice: explicit Endpoint Binding Service

NetSynth introduces a logical **Endpoint Binding Service**:

```text
resolve(EID) -> EndpointBinding
publish(EID, new binding generation)
```

The service is not a forwarding layer.

It is the rendezvous/control function that stores dynamic EID-to-LocatorSet information.

Why NetSynth chooses explicit resolution instead of name-independent routing:

1. Scale 4 already optimizes routing around topology-dependent Locators;
2. inter-Scope Route Programs are compiled from Locators;
3. stable endpoint attachment state changes at a different lifetime from routing topology;
4. moving EID lookup into every transit routing decision would mix two state domains that Scale 4 intentionally separated.

This does not imply that the Binding Service must be centralized.

## 8. Binding generations and cache semantics

A binding is versioned independently per EID.

A newer generation replaces the previous authoritative Locator Set.

Caches retain:

```text
EID
BindingGeneration
LocatorSet
remaining validity / refresh state
```

Older generations must not overwrite newer cached state.

Lifetime/lease bounds stale-cache duration, but correctness must not depend on globally synchronized clocks.

Push invalidation or direct peer update may later improve handover latency, but they are optimizations, not the only correctness mechanism.

## 9. Packet destination at Scale 5

For EID-targeted traffic, the packet logically carries both stable identity and current routing location:

```text
Destination EID
Selected Destination Locator
Hop Budget
Route / Transit Stack
Payload
```

The Locator drives Scale-4 route compilation and forwarding.

The EID survives attachment changes and is used at the destination attachment to identify the intended Endpoint.

This duplication is deliberate: identity and routing location are different information.

A future session/channel mechanism may compress repeated Endpoint information, but Scale 5 does not assume that yet.

## 10. Final delivery

A Locator terminates at a forwarding attachment position.

That local attachment maintains only local Endpoint-delivery state:

```text
EID -> local Endpoint delivery
```

The global Locator no longer needs to encode an Endpoint-specific local selector.

This avoids giving topology-dependent Locator components identity semantics again.

Local Endpoint state scales with locally attached Endpoints, not with the global Endpoint namespace.

## 11. Stale binding behavior

Suppose a sender cached:

```text
EID -> L_old
```

and the Endpoint has moved to `L_new`.

If `L_old` remains an active attachment, the packet may still succeed.

If it is no longer valid:
- the old attachment must not silently deliver the EID to a different Endpoint;
- delivery fails explicitly;
- the sender/ingress re-resolves the EID and compiles a new Route Program.

A mandatory forwarding pointer from old to new Locator is **not** part of the architecture.

This prevents mobility history from accumulating into routing paths.

## 12. Simultaneous mobility

Direct peer-to-peer locator update alone is insufficient when both peers move and lose each other's current location.

The Endpoint Binding Service provides the rendezvous fallback.

Therefore established communication can conceptually recover as:

```text
peer route/binding becomes stale
    -> resolve peer EID again
    -> obtain current Locator Set
    -> compile new Scale-4 Route Program
```

Transport/session continuity itself is a later-scale question.

## 13. What Scale 5 does not yet decide

Do not yet define:
- cryptographic identity;
- authentication/authorization of binding updates;
- human-readable names;
- service names;
- transport connections;
- reliable stream semantics;
- fast-handover protocol;
- Locator-selection policy among multiple attachments;
- Binding-Service storage topology;
- privacy mechanisms.

Those are distinct architecture questions.

## 14. Information placement

After this choice:

### Endpoint-local / binding authority

- stable EID;
- current attachment Locator Set;
- current BindingGeneration.

### Binding Service

- sharded authoritative EID -> binding records.

### Sender/ingress cache

- recently resolved binding records;
- Scale-4 Route Programs for selected Locators.

### Transit forwarding nodes

- no global EID-to-Locator database;
- unchanged Scale-4 STP/label state.

### Packet

- EID;
- one selected Locator;
- Route/Transit Stack.

Thus mobility state does not enter every transit router.

## 15. Graceful degeneration

A fixed infrastructure node may be addressed directly by Locator with no Endpoint Binding lookup.

A static application Endpoint can resolve once and cache for a long time.

A mobile/multihomed Endpoint updates only its binding state; Scale-4 routing topology need not change merely because the Endpoint moves between existing attachment positions.

## 16. Main architectural benefit

The key separation is not merely "ID versus address".

It is a **lifetime separation**:

```text
Endpoint identity          long-lived
Attachment binding         changes with mobility
Scope/Locator structure    changes with routing structure
Route Program              changes with selected path/binding
Pathlet realization        may change locally and frequently
physical queue/link state  fastest
```

Each faster-changing layer is prevented from forcing unnecessary changes in slower-lived state.

## 17. Next forced problem

The remaining Scale-5 problem is not whether identity should be separate.

It is:

> How should the Endpoint Binding Service distribute and update EID-to-LocatorSet records at global scale without replicating all Endpoint state everywhere or creating a single global bottleneck?

Before choosing that mechanism, reconcile with:
- LISP Mapping System/DDT;
- MobilityFirst GNRS/DMap;
- DHT/rendezvous systems;
- dynamic DNS;
- location services and caching consistency.

Only after that should the Binding Service architecture be fixed.
