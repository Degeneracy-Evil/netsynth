# Scale 4 Freeze Review

> Reviewed implementation through `d11cf7f20e046f027bd2a1f6ecf3f39c67043bf7`.
>
> Decision: **Scale 4 routing semantics are frozen.**
>
> This freeze covers architecture semantics, not wire encoding, production control protocols, performance tuning, or a claim of optimal routing theory.

## 1. Hardening result

The semantic prototype now enforces the blocking requirements from `docs/scale4-prototype-review.md`.

### Knowledge boundary

A Scope-owned persistent pathlet may use only:

- physical actions explicitly owned/visible at that Scope level;
- pathlet contracts exported by immediate children.

An ancestor cannot encode descendant-interior physical hops and cannot directly reference non-immediate descendant pathlets.

### Opaque query-time access

Source/destination Access realizations are retained in owner-local ephemeral `AccessRegistry` state.

The parent/ingress sees only the Access Offer metadata and opaque handle, not the realization.

### Contract validation

Publishing or repairing an STP validates the complete action sequence against owner-visible contracts:

- continuity from advertised ingress;
- continuity across every action;
- arrival at advertised egress;
- no hidden physical or descendant action.

Malformed hard contracts cannot enter active persistent state.

### Parent Route-Service view

`ScopeRouteService` is now constructed from:

- Scope ID;
- immediate-child IDs;
- boundary ownership;
- child BTGs;
- parent-owned crossing links.

It does not consume child interior membership or physical descendant topology.

### Generation safety

Historical generations are represented by a monotonically increasing per-slot high-water mark rather than an ever-growing tombstone set.

Stale exact handles cannot alias a newer generation.

### Destination delivery

The follow-up `d11cf7f` binds destination Access Offers to the owner-local target and the requested Locator. A destination offer for a different Locator fails closed.

## 2. Preserved Scale-4 semantics

The hardening did not change the architectural choices:

- Routing Scope is a laminar knowledge/control ownership structure, not a path constraint;
- Structured Locator is the Scale-4 topology-dependent destination coordinate;
- child-to-parent persistent state is a BTG of reusable STPs;
- routes may leave and re-enter Scopes;
- reusable summaries are pushed, destination-specific routes are pulled on demand;
- Route Programs carry coarse path state;
- Transit Stack executes pathlets recursively;
- internal pathlet repair may preserve a generation;
- soft metric changes do not invalidate the hard generation;
- hard failure retires the exact generation and stale references fail closed;
- small Scale-0/1/2/3 networks need no Scale-4 route-program machinery.

## 3. Original freeze criteria

All criteria from `docs/scale4-prototype-review.md` are now represented by implementation checks/tests:

1. no descendant-interior PhysicalHop in ancestor pathlets;
2. no non-immediate descendant pathlet reference;
3. owner-local opaque Access realization;
4. ingress-to-egress continuity validation;
5. owner-visible-contract-only validation;
6. no parent access to child interior topology/membership;
7. generation history O(number of used slots), not O(all past generations);
8. previous leave/re-enter, recursive execution, hidden repair, soft metric, stale-generation and small-scale semantics remain covered.

## 4. Non-blocking implementation caveat

The prototype is intentionally a semantic model.

Its executor can also be used in unit tests to execute a pathlet-only program that is not a complete end-to-end compiled route. Therefore the status name `delivered` should be read in that narrow test context as successful program completion unless a destination Access Offer is present.

Normal `ScopeRouteService.compile()` output requires a destination offer to reach its query-destination node, and the owner-local destination binding added in `d11cf7f` validates the requested Locator.

Do not expand Scale 4 merely to make the prototype API production-grade.

## 5. Freeze boundary

Do not add more Scale-4 routing mechanisms unless a later scale exposes a concrete contradiction.

Specifically, do not resume:

- prefix-monotone forwarding;
- Phase-6 sparse-metric repair;
- generic compact-routing plug-in architecture;
- global pathlet flooding;
- global routing epochs;
- new mutable-header abstractions beyond the chosen Route/Transit Stack.

Future work may revise Scale 4 only if a Scale-5+ requirement cannot be expressed without changing these semantics.

## 6. Next step

Return to first-principles derivation at **Scale 5**.

The first new problem is not another routing optimization. It is:

> What changes when a communicating entity can detach from one forwarding position and reattach elsewhere while existing communication should still refer to the same entity?

Before choosing an architecture mechanism, reconcile that problem with established identifier/locator separation, mobility, mapping/rendezvous, and name-independent-routing work.
