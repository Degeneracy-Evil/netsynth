# Phase 3.1 Review

> Reviewed implementation: `66da1b07b732860c7cdcf0cadad8ae8bb3ad6351`.
>
> Result: R0 successfully separates summary reachability from path-quality information. The remaining static failures are no longer summary-connectivity failures; they expose the lack of a globally coherent forwarding progress invariant.

## What Phase 3.1 established

R0 publishes exact connectivity components among stable Scope boundary interfaces without publishing exact distances. Its persistent summary representation is linear in the number of boundary interfaces and is composable bottom-up.

The small static suite delivered every ordered pair under R0, while S0/S1 still produced false `no_route` results. This validates the need for an explicit reachability floor independent of metric optimization.

The scaling experiment also confirms an important negative result: reachability compression is useful only where boundary complexity is small. On expander-like graphs, even R0 state can exceed the flat full-topology reference. This is consistent with the architectural hypothesis that an arbitrary graph may simply be poorly compressible.

## Main new finding: reachability is not forwarding coherence

The 128-node mesh produced static forwarding loops even though R0 preserved the required boundary connectivity.

This means two properties must be kept separate:

1. **Summary reachability:** the abstract representation preserves whether relevant interfaces are connected.
2. **Forwarding coherence:** independently compiled per-node FIB decisions form a directed acyclic progress structure toward the destination aggregate.

The current compiler gives each node a shortest abstract choice from its own personalized view. Different nodes may therefore make mutually inconsistent decisions. A collection of locally reasonable next hops need not form a globally coherent forwarding graph.

## Required invariant

For every destination aggregate/prefix `P`, converged forwarding needs a well-founded progress relation. A sufficient form is a scalar potential:

```text
phi_P(next) < phi_P(current)
```

for every legal forwarding edge while the packet remains at the same Locator resolution.

A finite forwarding graph satisfying strict potential descent cannot contain a stable loop.

The earlier Locator-prefix progress rule remains useful, but longest-common-prefix depth alone is too weak because many hops legitimately occur at the same resolution.

A useful combined progress order is lexicographic:

```text
(resolution progress, scoped potential)
```

where entering the target child increases Locator-prefix resolution, and otherwise each hop strictly decreases the current scoped potential.

## Failure result must stay separate

After a failure, a fixed Scope can become internally disconnected while the physical graph remains globally connected through a path that leaves and later re-enters that Scope.

This is not an R0 summary bug. Under the current prefix-monotone forwarding domain, such a detour is intentionally unavailable.

More importantly, if the destination's Scope splits, an external forwarder may know the boundary connectivity components but still not know which component contains the final destination. The stable Structured Locator does not encode that dynamic attachment.

Therefore arbitrary post-failure delivery cannot be guaranteed by boundary connectivity alone. Solving that later requires an explicit mechanism such as destination/component attachment information, temporary locator refinement, or scoped repair/path discovery. It must not be hidden inside the forwarding compiler.

## Next step

Before destination-attachment lookahead or decomposition optimization, add a converged **Scoped Potential Routing** control as the static forwarding-correctness floor.

The purpose is to answer a narrower question:

> Can the current Structured Locator hierarchy provide loop-free static delivery with only per-prefix scalar progress state rather than globally replicated topology?

Dynamic convergence and scope-break repair remain separate later questions.
