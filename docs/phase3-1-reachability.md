# Phase 3.1: Reachability-Preserving Summary Contract

> Status: corrective architecture experiment before destination-attachment optimization.
>
> Phase 3.1 does not change decomposition, Locator semantics, or data-plane forwarding. It establishes the minimum summary semantics required for a converged static network to avoid false `no_route` results.

## 1. Core invariant

For every scope `S`, define `B(S)` as the set of stable physical interface nodes in `S` incident to links leaving `S` in the reference topology.

A published summary is **reachability-preserving** iff, for any `a,b in B(S)` that remain present:

```text
physical path a -> b exists inside S
        iff
abstract summary path ref(a) -> ref(b) exists
```

For the candidate architecture, the important forbidden error is the false negative:

```text
physical path exists
summary says disconnected
```

False-positive reachability after failures is also unsafe for routing and should be represented explicitly as stale/control-plane state rather than silently accepted in the converged snapshot model.

The initial simulator continues to model converged snapshots, so the summary relation should match actual connectivity exactly at the reachability level.

## 2. Interface closure

Bottom-up composability is not enough. A non-leaf scope must be able to construct its own parent-facing summary using only child summaries and declared child-crossing links **without losing any of its own external interfaces**.

Every child summary consumed by a parent must therefore expose enough representation for all child boundary interfaces that can participate in:

- sibling transit inside the parent;
- ingress/egress of the parent itself;
- recursive construction of the parent's external summary.

This is the **interface-closure invariant**.

Do not select a bounded portal subset in a way that makes an unselected externally relevant boundary node unreachable to the parent abstraction.

## 3. Minimal reachability summary baseline

Add a new semantic baseline, name implementation-defined (for example `r0` or `connectivity`).

It should preserve boundary connectivity while publishing no claim of exact path cost.

A suggested representation is:

```text
boundary interface -> connectivity-component object
```

or an equivalent virtual-star/tree representation.

For a connected scope with `B` boundary interfaces, the logical state should be O(B), not O(B^2).

Requirements:

- virtual component/hub objects are control-plane abstraction only;
- they are not legal physical next hops;
- the personalized-view/FIB compiler may use them to establish existence of a route and to choose a deterministic feasible exit;
- the first data-plane hop remains a real adjacent physical neighbor;
- normalized state accounting must charge boundary references and virtual/component objects.

Exact encoding is not fixed.

## 4. Cost semantics

Do not pretend the minimal reachability representation knows exact metric cost.

The routing compiler needs a deterministic way to compare abstract alternatives. Test at least one deliberately weak policy, such as:

- every reachable abstract connectivity edge has uniform unit abstract cost; or
- component transit cost is unknown and tie-broken deterministically.

Actual path cost is measured only by the physical executor.

This baseline exists to answer:

> What stretch remains if the architecture guarantees reachability but exposes almost no remote metric information?

Later cost summaries are optimization layers over this correctness floor.

## 5. Existing S0/S1 interpretation

Keep current S0/S1 as historical/negative controls if useful, but do not treat false `no_route` on a connected converged graph as an acceptable property of the candidate routing core.

In particular:

- S0 demonstrates that crossing metadata without transit closure can be insufficient;
- current S1 demonstrates that bounded representative portals can violate interface closure.

A revised bundle strategy may sit above the reachability baseline only if it preserves the invariant.

## 6. FIB synthesis

Do not change the Phase-3 data-plane API.

The compiled runtime remains conceptually:

```text
next_hop(destination_locator, local_fib) -> physical_neighbor | no_route
```

The control-plane compiler may consume reachability abstraction objects in the personalized multiresolution view.

When an abstract route uses a remote virtual component, the compiler must still derive the owner's **first physical hop** using only owner-local detailed topology, charged crossing/interface references, and published summaries.

No full-graph fallback is allowed.

## 7. Correctness tests

Add exhaustive tests over connected static graphs.

At minimum:

1. tree families: every ordered source/destination pair is delivered under the reachability baseline;
2. mesh/torus: every pair is delivered;
3. several connected random and expander-like instances: every pair is delivered;
4. summaries satisfy the boundary connectivity relation for every scope;
5. non-leaf summary construction remains bottom-up and interface-closed;
6. abstract virtual nodes are never emitted as physical next hops;
7. after a failure that leaves source and target physically connected, converged forwarding must not report `no_route` because of summary information loss;
8. after a physical partition, unreachable pairs may report `no_route` and must not be silently repaired.

## 8. Failure locality

Re-evaluate locality using reachability summaries.

Classify failures into at least:

- internal metric/topology change with unchanged boundary connectivity;
- boundary reachability relation change;
- physical partition.

At the minimal summary level, only changes visible in the boundary-connectivity relation are inherently required to propagate upward.

## 9. Label sensitivity control

Retain the current end-to-end relabel experiment, but add a second isolated control where graph and ScopeTree are relabeled isomorphically while preserving the same structural decomposition.

The reachability guarantee must be invariant under node labels.

Route cost may vary under deterministic tie-breaking among structurally equivalent choices, but delivery success must not.

## 10. Modest scaling experiment

Once correctness passes, run several small/medium sizes, for example:

```text
16 -> 32 -> 64 -> 128
```

Sampling is allowed at larger sizes.

Report:

- normalized state per node and total;
- boundary count distribution;
- reachability-summary state;
- distributed stretch;
- failure-locality metrics.

Do not claim asymptotic complexity from these points; use them to detect obvious state explosion before Phase 4.

## 11. Exit criteria

Phase 3.1 is complete when:

1. connected converged graphs have zero false `no_route` under the minimum candidate summary;
2. every scope summary is demonstrably interface-closed and reachability-preserving;
3. the guarantee survives graph relabeling;
4. all runtime next hops remain physical and knowledge-disciplined;
5. state/churn/failure-locality accounting charges the new summary;
6. we have a clean stretch/state baseline for a network that can reliably find *some* path without destination-specific attachment information.

Only after this should Phase 4 add Locator-prefix/destination-attachment lookahead to improve ingress quality.
