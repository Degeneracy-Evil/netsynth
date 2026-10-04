# Scale 5 Freeze Review

> Reviewed implementation: `7f6c7fd0287442b246e05e3bc443e4eed426708b`.
>
> Decision: **Scale 5 endpoint identity and mobility semantics are frozen.**
>
> The freeze covers architecture semantics only. It does not freeze security, transport, distributed-storage implementation, resolver membership, consensus, or human/service naming.

## 1. Review result

The prototype remains deliberately small and sits above the frozen Scale-4 routing substrate.

It adds only:
- EndpointID;
- EndpointBinding;
- BindingService / BindingResolver semantic models;
- LocalAttachment exact-EID delivery;
- a mock upper-layer association used only to test identity continuity.

Scale-4 source and routing semantics remain unchanged.

## 2. Freeze criteria

All Scale-5 architecture-audit criteria are represented by direct implementation checks/tests.

### Stable identity

The same opaque EID survives binding versions and attachment changes.

### Multihoming

One EID may simultaneously map to several Locators and can be delivered correctly through either attachment.

### No routing churn from endpoint movement

Moving an Endpoint between already existing attachment positions changes Binding/local-delivery state but does not change Scope, BTG, STP, Route-Service, or pathlet-generation state.

### Safe stale binding

A stale binding may route a packet to an old forwarding position.

Final delivery is still exact by EID. If that EID is absent, delivery fails with `eid_absent`; a replacement Endpoint at the same Locator does not receive the packet.

Thus stale binding affects availability, not identity semantics.

### Explicit fresh resolution

After stale-delivery evidence, `resolve_fresh()` bypasses the normal valid-cache path and obtains current authoritative binding state.

A new Locator can then receive a new Scale-4 Route Program.

### Ordered per-EID versions

Binding versions are monotonic independently per EID.

Resolvers and the mock association reject older state and reject conflicting records that claim the same version.

### No global invalidation requirement

One resolver may refresh to a new binding while another continues using an older cached version.

Correctness still holds through final EID validation.

### Resolver bootstrap

Binding resolvers and authority groups are reached by Scale-4 Locators.

Locator-only infrastructure routing succeeds before any Binding Service or EID state exists, so there is no recursive EID-resolution dependency.

### Ongoing state remains EID-bound

The mock upper-layer association preserves its identity and application state while Binding, selected Locator, and Route Program are replaced.

No generic Channel object is required by Scale-5 mobility semantics.

### Locator-only traffic remains valid

Scale-4 infrastructure traffic works unchanged without Endpoint IDs or binding state.

## 3. Additional useful semantics

The prototype cleanly distinguishes:

- unknown EID: no authoritative record;
- temporarily unattached known EID: authoritative binding with an empty LocatorSet.

This preserves per-EID version continuity through break-before-make movement.

The authority owner is derived from the flat EID and does not move with the Endpoint attachment.

## 4. Non-blocking implementation limits

The following remain intentionally outside the Scale-5 freeze:

- the SHA-256 modulo toy sharding algorithm;
- authority-group membership changes;
- actual replication and consensus;
- persistent storage;
- cache eviction/reclamation;
- resolver RPC transport;
- publication authentication;
- fast peer-to-peer mobility hints;
- Locator selection policy;
- binding reachability probing.

These are implementation/distributed-systems concerns or later architecture questions, not contradictions in the Scale-5 semantic model.

## 5. Frozen Scale-5 architecture

For EID-addressed traffic:

```text
Endpoint ID
    |
    v
Endpoint Binding Service
    |
    v
BindingVersion + LocatorSet
    |
    v
selected Structured Locator
    |
    v
Scale-4 Scoped Route Resolution
    |
    v
Route Program / Transit Stack
    |
    v
selected attachment
    |
    v
exact local EID delivery
```

Transit forwarding retains no global EID table.

Mobility and multihoming are changes in Endpoint Binding state, not changes to the routing architecture.

## 6. Lifetime separation

The current architecture now has a clear state-lifetime hierarchy:

```text
Endpoint ID
BindingVersion / LocatorSet
Structured Locator
Route Program
STP generation
STP internal realization
physical link / queue state
```

Faster-changing state is increasingly local and does not automatically invalidate slower-lived identity/control state.

## 7. Freeze boundary

Do not add more Scale-5 mobility mechanisms unless a later scale exposes a concrete contradiction.

In particular, do not add by default:
- home agents / mandatory forwarding pointers;
- global EID FIBs;
- separate multihoming protocols;
- generic Channel IDs;
- globally synchronized Binding epochs;
- mandatory direct peer mobility updates.

## 8. Next architecture question

Return to first-principles derivation.

The next unresolved problem is no longer naming or routing:

> Once two stable Endpoints can find and reach each other, what communication semantics should the network provide when packets can be lost, duplicated, reordered, delayed, or traverse changing paths?

This is the point where transport/session semantics may finally be forced.

Before making a NetSynth choice, reconcile with:
- end-to-end arguments;
- TCP;
- QUIC;
- SCTP;
- MPTCP;
- RDP/RDP-like reliable datagrams;
- message-oriented versus byte-stream transport;
- congestion control and path-dependent state.

Do not assume TCP-like connection semantics or a universal Channel before that derivation.
