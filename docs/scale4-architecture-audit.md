# Scale 4 Architecture Audit

> Status: Scale-4 consolidation after architecture choices and theory reconciliation.

## 1. Scale-4 architecture in one sentence

NetSynth uses slow-changing laminar Routing Scopes to own and summarize routing knowledge; each Scope exports executable boundary transit pathlets; destination-specific inter-Scope routes are resolved on demand and carried as coarse packet forwarding programs; transit routers keep reusable pathlet state rather than a global destination FIB.

## 2. Final Scale-4 objects

### Routing Scope

A laminar control/knowledge ownership region. It is not a legal-path constraint.

### Structured Locator

A topology-dependent destination coordinate identifying the destination's Scope lineage and local selector. It is used by route resolution and final/local routing, not as a source route.

### Boundary Transit Graph (BTG)

The child-to-parent persistent routing summary. Vertices are real boundary interfaces; edges are advertised Scoped Transit Pathlets.

### Scoped Transit Pathlet (STP)

A reusable Scope-owned ingress-to-egress transit service with an opaque local forwarding handle. Its hard semantics are reachability/endpoints/generation; route-quality metrics are soft.

### Scoped Route Resolution

An on-demand control-plane computation over Scope-local BTGs and temporary source/destination access information. Persistent summaries are pushed upward; destination-specific routes are pulled when needed.

### Route Program / Transit Stack

One concept at two lifetimes:

- Route Program: the control-plane compiled sequence/composition of routing actions;
- Transit Stack: the packet-carried execution state for that program and recursively invoked STPs.

### Pathlet Generation

An immutable hard-contract version that prevents stale packet/program handles from aliasing new semantics.

## 3. Objects that are NOT first-class architecture layers

### Route Compiler

Only the ingress-side role that invokes Scoped Route Resolution and caches the result. It is not a separate network layer.

### Access Offer

Only a query-time result connecting a source/destination interior point to relevant boundaries. It should be represented by the same executable route-object semantics where practical, not promoted into a permanent protocol namespace.

### Generic RoutingScheme / Routing Descriptor

Useful simulator/research vocabulary, not Scale-4 NetSynth packet/control abstractions.

### Spanner / emulator / distance oracle / PCE

Theoretical or implementation tools. NetSynth may use known constructions internally, but they are not common-core packet objects.

## 4. Information placement by lifetime

### Very slow / structural

- Scope hierarchy;
- Structured Locator assignment rules;
- boundary membership;
- Scope ownership relationships.

### Scope-local persistent

- detailed local topology/routing state as needed;
- immediate-child BTGs;
- crossing-link state;
- STP forwarding realizations;
- Route Service data structures.

### Parent-visible persistent

- child BTG hard pathlet generations;
- soft routing metrics for those pathlets.

### Ingress/control cache

- destination-specific Route Programs;
- query results / temporary access information;
- known generation/refresh state.

### Packet-local

- Destination Locator;
- Hop Budget;
- Route/Transit Stack;
- Payload.

This explicit placement is the main Scale-4 architecture result.

## 5. Why Destination Locator stays in the packet

A compiled Route Program does not need to encode the exact final local forwarding path.

The large-scale program may terminate at the destination's final local Scope, where ordinary target-based routing uses the Structured Locator/local selector.

This preserves graceful degeneration:

- tiny/flat networks can use an empty Transit Stack and route only by Destination Locator;
- large networks add Route Programs only for the compressed inter-Scope portion.

The Locator also provides stable route-resolution context independent of one cached Route Program.

## 6. Header cost is explicit

Packet-carried route state is not free.

Two independent contributors exist:

- sequential STPs in the compiled abstract route;
- recursively pushed lower-level STPs while executing a composite pathlet.

Recursive nesting is bounded by Scope depth, but total header size can grow with abstract pathlet route length.

NetSynth accepts this because it deliberately moves destination-specific state away from transit routers. Header size must be measured during validation.

## 7. Hard validity versus soft route quality

Pathlet generation changes only when hard forwarding semantics change.

A metric increase, internal reroute, or quality change does not automatically invalidate a Route Program as long as the ingress-to-egress transit service remains realizable.

Soft metrics may be refreshed lazily. A stale metric may cause a suboptimal route; it must not cause incorrect forwarding.

Fast queue/congestion state should not be exported as a hard Scope contract. It belongs primarily to local scheduling/multipath mechanisms unless a later architecture question proves otherwise.

## 8. Change propagation

### Internal hidden change

STP remains realizable -> local repair only.

### Soft metric change

May update parent selection information, but does not invalidate existing Route Programs.

### Hard STP failure

Withdraw generation; only Route Programs depending on that generation become stale.

### Scope structural change

May require Locator/ownership restructuring and is intentionally a slower class of event not solved by ordinary routing repair.

This separation is more important than exact shortest-path maintenance.

## 9. Graceful degeneration to Scale 0-3

### Two-node link

No hierarchy or Route Program is necessary.

### Small branching network

One flat local Scope; Destination Locator/local selector chooses forwarding target.

### Small/medium dynamic mesh

A single Scope may use ordinary local routing/control. Transit Stack remains empty. Hop Budget still bounds transient inconsistency.

### Large network

Nested Scopes and Route Programs appear only because global persistent knowledge becomes too expensive.

Thus Scale 4 adds machinery only where the earlier model actually fails.

## 10. Non-compressible graphs

NetSynth does not claim that Scope summaries are small on every arbitrary graph.

Expansion/high boundary complexity may force a Scope's BTG or query state to become large. Known compact-routing/spanner lower bounds explain why no universal architecture can make all such information disappear.

The honest degradation mode is:

- keep the architecture semantics;
- allow the difficult Scope to remain flatter or expose more pathlet state;
- accept the measured state/header/stretch cost;
- do not create artificial hierarchy solely to make metrics look good.

## 11. Prior-art audit

### Pathlet Routing

Already provides path fragments, local FIDs, recursive pathlet composition, and packet-carried FID sequences.

NetSynth difference: pathlets are owned/exported through topology-derived laminar Scopes, destination-specific pathlet graphs are not globally disseminated by default, and route selection is a network-side pull computation rather than source-controlled global route selection.

### SCION

Already provides path-segment discovery/registration, on-demand lookup/caching, and packet-carried forwarding state.

NetSynth difference: no AS/ISD/security architecture is assumed; Scopes are topology/control compression regions, and route programs are network-selected rather than an application path-control primitive.

### Hierarchical PCE

Already provides recursive path computation where parent PCEs see child-domain interconnection but not child internals.

NetSynth difference: this principle is integrated into the normal network routing architecture with reusable Scope pathlets and packet-carried programs, rather than being an MPLS/GMPLS traffic-engineering subsystem.

### MPLS / Segment Routing

MPLS supplies the mature local label-stack execution primitive. Segment Routing demonstrates headend-carried path instructions.

NetSynth does not claim either idea as new and does not import their compatibility/protocol ecosystems.

## 12. What is actually distinctive

Scale 4 is best understood as a deliberate synthesis, not a new routing theorem.

The distinctive architectural combination is:

    topology-derived laminar control ownership
    + opaque executable boundary contracts
    + local repair behind stable pathlet identity
    + push only reusable summaries
    + pull destination-specific routes
    + network-compiled packet-carried coarse path state
    + simple label-switching transit forwarding

Whether this combination is better than the strongest alternatives is an architecture question to validate, not a novelty claim.

## 13. Remaining known weak points

### Query complexity

Source/destination Access Offers may be large when a child has many boundaries. Existing path-reporting/oracle theory should be used if this becomes a bottleneck.

### Header size

Route Program size can grow with abstract path length.

### High-level control hot spots

Very high-level Scope Route Services may receive many route queries. Their state is small/slow enough to replicate in principle, but replication/load is not free and must later be validated.

### Poorly compressible topologies

Root/upper Scope BTGs can still be large. This is an inherent architecture limitation rather than something to hide with simulator tuning.

### Route failure feedback

A stale Route Program fails closed, but fast notification/retry semantics have not yet been derived because transport/source-feedback semantics are not yet in the architecture.

## 14. Scale-4 freeze candidate

No additional Scale-4 routing primitive is currently justified.

Before proceeding to Scale 5, the architecture needs only a **minimal semantic validation**, not another broad experiment phase.

The validation should test:

1. recursive BTG/STP composition without descendant-topology leakage;
2. arbitrary leave/re-enter routing through Scope graphs;
3. push-summary / pull-route resolution;
4. Route Program + Transit Stack execution;
5. hidden local reroute preserving pathlet generation;
6. hard failure causing stale handles to fail closed without aliasing;
7. Scale-0/1/2/3 cases working with empty/minimal Scale-4 machinery;
8. explicit persistent-state, query-state and packet-header accounting.

Do not use the validation to rediscover compact-routing/spanner asymptotics.

## 15. Decision after validation

If these semantics work without hidden global knowledge or unbounded accidental state, freeze Scale 4 and resume first-principles derivation at Scale 5: attachment change, mobility, and stable identity.

If they fail, revise the architecture before adding Endpoint identity or transport.