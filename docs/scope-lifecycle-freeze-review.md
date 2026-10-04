# Scope Lifecycle Freeze Review

> Reviewed implementation: `2467f356f21d7bafd9bff7a08741559327d87db1`.
>
> Decision: **the NetSynth Routing Scope lifecycle is frozen.**
>
> This freeze covers Scope formation, steady-state ownership, local repair, structural split/merge, Locator renumbering, make-before-break layout transition and flat fallback. It does not freeze one partition algorithm, one universal budget function, or one rollout protocol.

## 1. Review result

The prototype remains deliberately narrow.

It adds a structural-control semantic layer around the already frozen Scale-4/5/6 substrate without changing those source semantics.

The implementation uses:
- one stable RoutingScope ownership object;
- Scope-local LayoutGenerations;
- generation-qualified Structured Locators;
- two-layout make-before-break coexistence;
- frozen Scale-5 multi-Locator Binding;
- existing Route Program / STP execution;
- explicit control-state and migration-cost accounting;
- a toy hysteretic formation policy over hand-selected candidate layouts.

No generic partition search, separator framework, path-stretch sweep or global routing epoch is introduced.

## 2. Freeze criteria

All fourteen criteria requested by `docs/scope-formation-policy.md` / the development prompt are represented by direct implementation checks/tests.

### Per-generation laminarity

Each LayoutGeneration is independently validated as a disjoint exact Scope partition with connected leaf interiors.

Two generations may coexist during migration, but overlap occurs only **between versions**, not within one active layout definition.

Thus migration does not reintroduce arbitrary overlapping Scope membership.

### Locator generations cannot alias

Locator semantics include the Scope-local layout generation.

The tests deliberately reuse:
- the same child label;
- the same selector;

for different physical positions across generations and verify that the Locators remain distinct.

A Locator from generation g1 cannot be compiled as a destination in g2.

### EID / Channel survive renumbering

Endpoint identity remains stable while Bindings progress through:

~~~text
{ old Locator }
    -> { old Locator, new Locator }
    -> { new Locator }
~~~

The same EID-bound Scale-6 Channel, Receive Tokens, Packet/Message number state and receiver credit survive the Route-Program replacement.

Structural routing change therefore does not redefine communication identity.

### Old layout remains usable during overlap

After the new layout is activated, the old layout remains active until explicit retirement.

Existing old Route Programs continue to execute using their old generation-qualified Access/STP state.

### New layout can serve new traffic

Once activated, new Locators compile and execute through the new layout while the old layout remains valid.

No flag-day switchover is required.

### Retirement fails closed

Retirement removes/invalidates old owner-local query state and retires old child pathlets.

Stale state then fails through explicit mechanisms:

- old layout entry: `stale_layout`;
- cached Access realization: `missing_access_state`;
- cached child pathlet: `stale_pathlet`.

Retired generation numbers cannot be reused.

### Parent hard contract can remain stable

A Scope can rebind an existing parent-visible STP handle to a realization built solely from:
- current layout crossing links;
- immediate-child STP contracts.

When ingress/egress/handle semantics remain unchanged, no parent hard update occurs.

A cached parent transit handle therefore remains valid while the Scope changes its internal child layout.

A previously withdrawn external hard handle cannot be silently resurrected by a later layout activation.

### No global configuration epoch

Generation state is local to each Routing Scope.

Disjoint Scopes advance layout generations independently.

Nothing in packet/control semantics requires a network-wide configuration number.

### Budget accounting includes local and exported state

The prototype explicitly charges:
- owner/layout metadata;
- Route-Service state;
- pathlet/realization state;
- child boundary records;
- child BTG pathlets;
- parent-visible boundary/pathlet records;
- exported hard-update count.

Flat and split layouts therefore cannot gain an artificial advantage by declaring wrapper/control objects free.

### Structural transition cost is explicit

The toy migration cost charges:
- reconstruction of new control state;
- every forwarding position whose Structured Locator changes;
- Binding publications for affected Endpoints;
- simultaneous old/new state during overlap;
- parent-visible hard updates where applicable.

The field named `renumbered_attachments` in the prototype is best interpreted as **renumbered forwarding/attachment positions**, not the number of Endpoint objects.

Endpoint Binding churn is accounted separately through `affected_endpoints -> binding_publications`.

This naming detail is not an architecture semantic and does not block the freeze.

### Hysteresis prevents thrashing

A candidate must show persistent benefit across several observations and enough expected long-run gain to amortize migration cost plus a safety margin.

One-record or transient improvements are rejected.

The concrete weights/horizon are fixture values only, not frozen constants.

### Modular split can be beneficial

On the modular fixture, splitting lowers maximum per-controller pressure enough to justify:
- somewhat higher aggregate local state;
- explicit migration cost.

This validates that Scope hierarchy can trade aggregate state for bounded control ownership rather than pretending every hierarchy must reduce every metric simultaneously.

### Poorly separable topology may remain flat

On the dense/poorly separable fixture, the split:
- barely improves peak controller state;
- nearly doubles aggregate local state;
- increases boundary/pathlet state.

The policy rejects it, and a flat layout remains valid.

This confirms the frozen rule:

> hierarchy is optional control compression, not a correctness requirement.

### Route correctness is independent of hierarchy geometry

Both flat and split layouts are exhaustively checked on the tiny fixtures.

A test route explicitly leaves and later re-enters the same child Scope to avoid an expensive internal physical edge.

Therefore the structural implementation preserves the core rule:

~~~text
Scope hierarchy = control / knowledge ownership
physical path    = arbitrary valid graph path
~~~

## 3. Hidden-topology review

The structural controller receives exactly the physical subgraph owned by its Routing Scope.

Leaf owners receive only induced local graphs.

The runtime ScopeRouteService still receives only:
- immediate-child IDs;
- boundary ownership;
- child BTGs;
- crossing links.

Tests disable detailed/global shortest-path planners while parent-level activation/route resolution continues.

The full physical graph is used by the semantic executor as a correctness validator, not as a hidden parent routing oracle.

No blocking global-topology leak was found.

## 4. Formation-policy interpretation

The toy policy is not a NetSynth routing theorem.

It exists only to validate that all required costs can influence a restructuring decision.

The frozen architecture commits to the dimensions:

~~~text
local control pressure
aggregate local state
parent-visible contract size
hard export churn
structural migration cost
persistent benefit / hysteresis
~~~

It does **not** commit to:
- their current integer weights;
- one scalar objective;
- one horizon;
- one automatic partition algorithm.

Deployment profiles may make different tradeoffs.

## 5. Frozen Scope lifecycle

The complete Scope lifecycle is now:

~~~text
physical/control region
        |
        v
connected control-budgeted Scope formation
        |
        v
steady-state child BTG / STP summaries
        |
        +-- ordinary topology change
        |       -> owner-local repair
        |
        +-- persistent structural pressure
                -> evaluate split / merge candidate
                -> charge migration + renumbering
                -> require hysteretic benefit
                        |
                        v
                 prepare Layout g2
                        |
                 g1 + g2 coexist
                        |
                 old/new Locator Bindings
                        |
                 move new route compilation to g2
                        |
                 retire g1
                        |
                 stale g1 references fail closed
~~~

If no useful partition exists, the region remains flat.

## 6. Freeze boundary

Do not reopen Scope architecture merely to optimize one layout metric.

In particular, do not add by default:

- prefix-monotone routing;
- fixed fanout/depth;
- mandatory recursive partitioning;
- overlapping steady-state Scope membership;
- a global configuration epoch;
- another permanent attachment/Locator indirection layer;
- traffic-hotspot-driven rapid repartitioning;
- a universal separator/partition algorithm;
- fake hierarchy for expander/noncompressible regions.

A later requirement may reopen one of these choices only if the frozen lifecycle creates a concrete contradiction.

## 7. Non-blocking implementation limits

The semantic prototype does not define:

- durable generation allocation after controller restart;
- exact drain/expiry timers;
- asynchronous activation-failure recovery;
- multi-level reparenting rollout;
- production benefit estimators;
- exact control-budget units;
- wire encoding of generation-qualified Locators;
- automated partition candidate generation.

These are implementation/control-plane engineering questions or later research questions, not current architecture contradictions.

## 8. Architecture status

With this freeze, the Scope line is complete enough to stop iterating on hierarchy:

- why Scopes exist;
- what they export;
- how routes cross them;
- how they absorb ordinary failure;
- how they are formed;
- how bad partitions are rejected;
- how split/merge occurs;
- how Locators are renumbered;
- how old/new layouts coexist;
- how structural change remains local when parent hard contracts are preserved.

Future work should move to a genuinely different network requirement.

## 9. Next first-principles direction

A natural unresolved capability is **one-to-many / group communication**.

The architecture so far is fundamentally point-to-point:

~~~text
Endpoint -> Endpoint
~~~

A next derivation can ask:

> When the same information must reach many Endpoints, should NetSynth provide any network-level replication/group primitive, or should applications always create independent Channels?

This is especially relevant to:
- replicated services;
- publish/subscribe;
- distributed systems;
- HPC / AI collectives.

The question should be derived from first principles and reconciled with IP multicast, application-layer multicast, pub/sub, multicast trees and collective communication before adding any group primitive.

Do not start implementation until that architecture choice is made.
