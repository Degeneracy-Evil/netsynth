# Scale 5: Global Endpoint Binding Service

> Status: architecture choice after theory reconciliation.
>
> This document fixes the global storage/lookup semantics for Scale-5 EID-to-LocatorSet bindings. It does not prescribe one storage-engine implementation.

## 1. Requirements

The Binding Service must support:

- a flat opaque Endpoint-ID namespace;
- very large numbers of Endpoint records;
- frequent attachment updates;
- one-to-many EID-to-LocatorSet bindings;
- on-demand lookup and edge caching;
- bounded replication rather than global replication;
- no circular dependency on EID resolution to reach the resolver itself;
- safe operation with temporarily stale caches.

The service is a control-plane distributed key-value function, not part of transit forwarding.

## 2. Prior-art reconciliation

### LISP Mapping System / DDT

LISP cleanly separates mapping lookup from forwarding and uses Map-Resolvers plus authoritative mapping servers.

LISP-DDT provides scalable hierarchical delegation when the EID namespace has prefix structure.

NetSynth adopts the resolver/cache/authority separation and the rule that mapping infrastructure is reached by routable Locators, not by the identifier namespace it resolves.

NetSynth does not adopt prefix-delegated EID authority because Scale-5 EIDs are intentionally flat and opaque.

### MobilityFirst DMap

DMap stores dynamic identifier-to-locator mappings by applying consistent hash functions to identifiers and distributing records across network locations. This directly addresses flat-name sharding and high mobility.

### MobilityFirst Auspice / GNRS

Auspice shows that dynamic replication can trade lookup latency, update cost and availability according to demand.

NetSynth treats demand-aware replica placement as an implementation technique, not a new architectural layer.

### Dynamic DNS

DNS demonstrates global caching and delegation extremely well for mostly slow-changing hierarchical names, but TTL-heavy cache invalidation and hierarchical naming are a poor default fit for the high-update flat EID workload.

## 3. Architecture choice: flat sharded authority

The Endpoint Binding Service is logically a global distributed table:

```text
EID -> EndpointBinding
```

The flat EID key deterministically maps to a **small authoritative replica group**.

Authority placement is independent of:
- the Endpoint's current Locator;
- the Endpoint's current Routing Scope;
- human-readable naming hierarchy.

This is crucial: mobility changes the binding value, not the ownership location of the binding record.

A consistent/rendezvous-hash style assignment is the preferred implementation family.

Exact replication factor, hashing algorithm, and membership protocol are implementation choices.

## 4. Resolver role

Every source/ingress may use a nearby logical **Binding Resolver**.

The resolver:
- serves a valid local cache entry when available;
- otherwise locates the authoritative replica group;
- obtains a binding;
- caches the result;
- returns it to the caller.

Resolvers themselves are infrastructure objects reachable directly by Scale-4 Locators.

They do not require EID resolution to bootstrap.

## 5. Binding record

Conceptually:

```text
EndpointBinding {
    EndpointID
    BindingVersion
    LocatorSet
    CacheLifetime
    soft metadata?
}
```

`BindingVersion` is totally ordered **per EID**, not globally.

The architecture requires only that a client can distinguish newer from older binding state.

No global clock or global mapping epoch is required.

## 6. Publication

An Endpoint or its authorized attachment-side control function publishes a new complete Locator Set.

Conceptually:

```text
publish(EID, LocatorSet)
    -> new BindingVersion
```

The update goes to the EID's authoritative replica group.

The Binding Service does not broadcast the update to every ingress or transit router.

How publication authority is authenticated is explicitly deferred to the security architecture.

## 7. Cache consistency choice

NetSynth deliberately does **not** require globally synchronous cache invalidation.

A resolver cache may temporarily return an older BindingVersion.

Safety comes from the architecture outside the cache:

- the packet also carries the stable EID;
- an old attachment that no longer hosts that EID must not deliver it to another Endpoint;
- failed/stale delivery triggers refresh.

Stale bindings therefore reduce availability/path quality temporarily but do not change Endpoint identity.

This lets binding updates remain local to the authoritative storage/replica machinery instead of becoming a network-wide transaction.

## 8. Fresh lookup

Ordinary lookup may use cache:

```text
resolve(EID)
```

After evidence that cached state is stale, the requester needs a stronger operation:

```text
resolve_fresh(EID, known_version?)
```

which bypasses or revalidates local stale cache state against authoritative storage.

This prevents repeated retry against the same expired Locator Set.

The exact protocol spelling is deferred; the semantic distinction is architectural.

## 9. Cache lifetime

Cache lifetime limits passive staleness and bounds forgotten records.

It is not the sole correctness mechanism.

Short lifetimes reduce stale mobility mappings but increase lookup load; long lifetimes do the reverse. Auspice-like adaptive caching/replication may optimize this later.

The architecture does not choose one universal TTL.

## 10. Read/write locality

Writes are routed to a small EID-authoritative replica group.

Reads are normally served from:
- a nearby resolver cache;
- a nearby read replica where deployed;
- the authoritative group on a miss.

Thus:
- Endpoint movement does not update all routers;
- popular stable EIDs can be replicated near demand;
- highly mobile EIDs need not invalidate all copies synchronously.

## 11. Failure semantics

If some authoritative replicas are unavailable:
- cached records may continue to be used within their validity policy;
- fresh writes/strong refresh may temporarily fail;
- the routing plane remains unaffected for already known valid Locators.

Availability/consistency of the authoritative replica group is a distributed-systems problem.

NetSynth does not invent a new consensus protocol.

## 12. Interaction with multihoming

The Binding Service stores the complete current Locator Set.

Selection among Locators is performed by the sender/ingress using:
- reachability;
- path setup result;
- optional soft preference/cost metadata.

The Binding Service does not create a second multihoming routing protocol.

## 13. Interaction with Scale-4 route state

The source-side state chain is:

```text
EID
  -> cached BindingVersion + LocatorSet
  -> selected Locator
  -> cached/compiled Route Program
```

These caches have different invalidation domains.

### Pathlet failure

First recompile/re-resolve the Scale-4 route to the **same Locator** when appropriate.

### Attachment rejection / EID absent at selected Locator

The binding is definitely stale for that attachment:
- invalidate that selected attachment locally;
- perform fresh EID binding resolution.

### Locator unreachable

The source may:
- try another Locator from the same BindingVersion;
- recompile a route;
- refresh the binding when evidence suggests attachment movement.

This prevents every path failure from becoming a global name lookup.

## 14. Negative bindings

The authoritative service may return an explicit current "no active attachment" record:

```text
EID -> {}
```

This is distinct from "unknown EID".

Negative results may be cached for a bounded period, but must be refreshable because break-before-make movement can create temporary emptiness.

## 15. No binding hierarchy in Endpoint IDs

The EID bit pattern has no routing/database-prefix meaning.

Any sharding prefix or hash bucket is internal to the Binding Service and may change without changing Endpoint IDs.

This avoids coupling identity lifetime to resolver topology.

## 16. State placement

### Authoritative binding storage

Approximately O(number of Endpoints x bounded replication factor) total records.

### Resolver/edge cache

Demand-dependent subset of bindings.

### Transit routers

No EID mapping table.

### Routing Scopes

No mandatory Endpoint bindings.

### Packet

Current EID plus selected Locator.

This separation is the primary scaling property.

## 17. What is not architecture novelty

NetSynth does not claim novelty for:
- flat identifier-to-locator mapping;
- consistent-hash/DHT sharding;
- demand-aware replica placement;
- mapping caches;
- EID/RLOC separation.

These are established ideas.

The architecture choice is to place this mapping service **above the frozen Scope/Route-Program routing substrate**, with stale-cache safety explicitly provided by EID-preserving final delivery.

## 18. Remaining Scale-5 question

At this point new communication can find a moved Endpoint.

The next question is different:

> What state must survive at the communicating endpoints so that an **ongoing conversation** can continue across binding/Locator changes rather than being treated as a brand-new exchange?

This is where a Channel/session abstraction may finally be forced.

Before choosing it, reconcile with:
- HIP associations and mobility updates;
- QUIC connection IDs / connection migration;
- MPTCP;
- SCTP multihoming;
- MobilityFirst mobile sockets;
- connection identifiers and transport-state migration.

Do not introduce transport semantics before that reconciliation.
