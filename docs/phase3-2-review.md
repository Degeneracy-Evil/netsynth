# Phase 3.2 Architecture Review

> Reviewed implementation: `a2070da82fe50210843fa59ff602c8f9c64b5688`.
>
> Result: Phase 3.2 closes the converged static-forwarding correctness problem for a fixed, scope-connected hierarchy. The next architectural question is no longer reachability or loop freedom; it is how much deeper destination attachment information is worth exposing to improve ingress choice.

## What is now established

The scoped-potential candidate is materially cleaner than the earlier summary-driven FIBs:

- the packet carries a Structured Locator;
- each Scope maintains scalar potentials only for scoped destination keys;
- potentials can be obtained by neighbor-to-neighbor Bellman fixed-point updates;
- forwarding exposes an eligible set of adjacent physical neighbors whose potential is strictly lower;
- deterministic single-next-hop selection is only an experiment policy;
- R0 is not consumed by the candidate architecture.

The implementation does not call a shortest-path planner when converging scoped potentials, and tests explicitly verify this boundary.

## Static correctness invariant

For an active Scope `S` and target child prefix `P`, let

`phi[S,P](u)`

be the converged shortest metric from node `u` to the sink set represented by `P`, restricted to the induced physical graph of `S`.

If the induced graph of `S` is connected, every non-sink node with finite potential has at least one physical neighbor with strictly smaller potential. Therefore forwarding only along strict-descent neighbors cannot form a cycle and must reach the sink set in finitely many hops.

After entering the target child, Locator-prefix resolution increases and forwarding switches to the next Scope. Since hierarchy depth is finite, repeated scoped descent reaches the leaf-local destination.

Thus, under converged state and while every Scope on the forwarding hierarchy remains connected:

- all reachable destinations are delivered;
- stable forwarding loops are impossible;
- Hop Budget is not needed for steady-state correctness, though it remains useful for inconsistent/transient state.

The implementation results are consistent with this invariant.

## R0 status

R0 remains useful as an experimental reachability/compression baseline, but it is not required by the current candidate routing core.

The candidate core is now better described as:

```text
Structured Locator
      +
scoped prefix potentials
      +
strict-descent eligible next-hop sets
```

## Remaining path-quality problem

Phase 3.2 routes toward the immediate target child as a sink set. It therefore optimizes:

`distance(current, any ingress into target child)`

rather than:

`distance(current, an ingress that is good for the final destination)`.

This explains why static delivery and loop freedom can coexist with very poor weighted stretch.

The worst observed stretch of 39 is not a reachability failure. It is an information-resolution failure.

## Two different sources of stretch

Future experiments must distinguish:

1. **information-resolution stretch** — the node knows only a coarse target prefix and therefore chooses a poor ingress;
2. **hierarchy-constraint stretch** — even with complete destination attachment information, the best path that never leaves a target Scope after entering it may be longer than the unrestricted physical shortest path.

These must not be conflated.

## Scope-breaking failures

A physical graph can remain connected while an induced Scope becomes disconnected. In that case a valid physical detour may require leaving the Scope and later re-entering it.

The present progressive-resolution rule deliberately forbids that. This is not a missing potential edge; it is a limitation of prefix-monotone forwarding.

Do not fix this in the next phase. First quantify the best path quality achievable *within* prefix-monotone semantics.

## Dynamic convergence

The current Bellman computation models converged synchronous state. Asynchronous updates, stale advertisements, transient loops, message volume, and convergence timing remain unresolved.

This does not block the next information-budget experiment because Hop Budget already bounds transient inconsistency conceptually. Dynamic-control-plane semantics should be studied after the steady-state forwarding information tradeoff is better understood.
