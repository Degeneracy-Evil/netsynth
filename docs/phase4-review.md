# Phase 4 Architecture Review

> Reviewed implementation: `f9ec2322df3b061a1210c36bc6690c2e60ebdbb5`.
>
> Result: bottom-up attachment lookahead is knowledge-disciplined and preserves the Phase-3.2 forwarding invariants. Phase 4 successfully separates information-resolution loss from the loss imposed by prefix-monotone hierarchy itself.

## What Phase 4 established

The implementation keeps the packet format unchanged. A child publishes only boundary attachment values derived from its own converged potentials; the parent does not inspect descendant topology and does not call a path planner.

The important empirical result is that finite lookahead has a useful state/stretch region, while full lookahead becomes much more expensive than Flat on larger graphs. More importantly, full lookahead still has nontrivial stretch relative to Flat.

Therefore the remaining full/Flat gap is not an attachment-information shortage. It is hierarchy constraint.

## Full lookahead interpretation

Full lookahead should be interpreted as the shortest route under the current prefix-monotone semantics:

- forwarding may move arbitrarily inside the active Scope;
- once it enters the target child Scope, Locator resolution increases;
- it may not later leave that child and reduce resolution;
- the same rule applies recursively.

This is the correct reference for evaluating Scope decomposition.

## Scope isometry criterion

Let `G[S]` be the physical graph induced by Scope `S`.

Define `S` to be isometric when, for every `u,v in S`,

```text
d_G[S](u,v) = d_G(u,v)
```

where distance uses the physical link metric.

This condition exactly captures the route-quality requirement created by prefix-monotone forwarding.

### Necessity

If `u` and `v` already lie in the same Scope, their Locator match already includes that Scope. Prefix-monotone forwarding cannot leave the Scope without decreasing resolution.

Therefore if some pair has

```text
d_G[S](u,v) > d_G(u,v)
```

that pair necessarily suffers hierarchy stretch.

### Sufficiency

If every Scope in the laminar hierarchy is isometric, a physical shortest path can be transformed recursively so that after it enters each target-containing child it never needs to leave that child, without increasing cost.

Thus an all-isometric ScopeTree admits a shortest prefix-monotone path for every source/destination pair.

Under exact full attachment, the simulator should recover that constrained shortest path.

## New architecture principle

Scope quality is not only about separator size or community structure.

A useful Scope must balance:

1. **compression** — small externally visible boundary/state;
2. **metric closure** — routes between members should not gain much by leaving the Scope;
3. **failure stability** — small changes should not constantly invalidate the Scope;
4. **reasonable balance/depth** — enough hierarchy to reduce state.

The first two are in direct tension on some graph families.

This gives a more precise interpretation of hostile graphs: expander-like or highly shortcut-rich graphs may simply have few large subgraphs that are both low-boundary and approximately isometric.

## Scope distortion metric

For a Scope `S`, define its internal escape distortion by the distribution of

```text
escape_ratio_S(u,v) = d_G[S](u,v) / d_G(u,v)
```

for member pairs with finite distance.

Useful reports include mean, p95, p99, max, and fraction exactly one.

A weighted graph must use weighted distance. Hop-only geometry is insufficient: a cheap external shortcut can make an apparently good unweighted Scope highly non-isometric.

Also report boundary complexity separately. Do not collapse distortion and boundary state into one score in primary results.

## Finite-lookahead note

The current finite `h=2` and `h=3` implementation uses absolute Locator-depth segment checkpoints so no extra packet state is needed.

These strategies are valid, but their information sets are not strictly nested. Therefore `h=3` is not mathematically guaranteed to dominate `h=2`, which explains the observed instance where h=3 is slightly worse.

Do not use monotonicity across finite h as a correctness requirement. Use `full` as the clean hierarchy reference.

## Scope escape

Allowing a packet to leave a target-containing Scope after entering it would directly relax the source of hierarchy stretch, but it would also break the simple monotonic progress invariant and require additional information about how to leave and re-enter safely.

Do not add Scope escape yet.

First determine whether better Scope formation can make the prefix-monotone model sufficiently good.

## Next step

Phase 5 should make decomposition an experiment axis while keeping forwarding semantics fixed.

The primary question is:

> Can we form large, low-boundary, approximately isometric Scopes well enough that prefix-monotone routing retains its state advantage without significant hierarchy stretch?
