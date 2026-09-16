# Phase 2 Architecture Review

> Reviewed implementation: `6ea999b6c69f822b73b304f70a50e50afe551c8f`
>
> Result: Phase 2 substantially improves information accounting and summary composability, and its negative boundary-complexity results are important. However, current path-quality results for S1-S3 are optimistic because route construction can recursively query exact routing inside remote child scopes. The next phase must close this knowledge-boundary leak before decomposition optimization.

## What Phase 2 established

Phase 2 successfully unified several pieces that were inconsistent in Phase 1:

- summaries are built bottom-up;
- non-leaf summary construction consumes immediate-child summaries plus declared crossing information;
- persistent forwarding/control objects are charged by semantic category;
- failure locality is strategy-specific and compositional;
- all strategies run on the same topology, decomposition, pair samples, and failure events;
- paths are validated as physical simple paths.

The state result on high-boundary-complexity graphs is already meaningful: full boundary metric closure can cost more than flat full-topology state. This is a real architectural warning and must not be optimized away by special cases.

## Main findings

### 1. S1 being smaller than S0 is valid, but S0/S1/S2/S3 are not a monotonic information ladder

S0 keeps every crossing-link object. S1 replaces those objects with bounded boundary bundles and representative crossings, while also adding useful derived portal distances. Therefore S1 can contain less normalized state than S0 while routing better.

This is not a contradiction. It means representation quality matters in addition to raw information quantity.

Future analysis should treat the strategies as points in a state/quality design space rather than assume `S0 < S1 < S2 < S3` in total information or state.

### 2. Current S1-S3 route construction crosses an architectural knowledge boundary

`CompressedRouting._route_overlay()` builds an abstract route at a parent scope. To evaluate possible interfaces in the target child it recursively calls exact routing inside that child, including routes from each candidate interface to the final target.

Those exact destination-specific costs are not contained in the target child's published summary and are not stored at the parent/source node. The simulator therefore uses information that the declared ownership model does not give to the routing decision maker.

The same issue appears when exact internal routes are queried while evaluating alternatives that leave and re-enter a scope.

This should be viewed as a **recursive path oracle**, not yet as deployable distributed forwarding.

### 3. S2(k=1) near-shortest and S3 exact-shortest results are therefore upper bounds, not architectural results

A boundary-to-boundary metric summary describes how traffic can traverse a scope. It does not, by itself, provide the exact distance from every boundary to every arbitrary interior destination.

For an external decision maker to choose the globally optimal ingress for an arbitrary endpoint, at least one of the following must exist:

- destination-specific routing/metric state;
- additional locator information that encodes useful internal attachment/path information;
- an explicit query/path-computation mechanism into the destination scope;
- or a weaker routing objective that does not require globally optimal ingress selection.

All of these have architectural costs. None should be introduced implicitly.

Therefore the current S3 result proves something narrower but still useful:

> with exact composable boundary summaries plus recursive access to exact child routing, the fixed decomposition itself need not destroy shortest paths.

It does **not** prove that boundary summaries alone are sufficient for shortest-path distributed forwarding.

### 4. Summary construction itself is correctly compositional under the current model

The Phase-2 builder is materially better than Phase 1: a non-leaf scope constructs its available abstract graph from immediate-child published summaries and declared crossings. This should be preserved.

The next correction belongs primarily in route execution/decision semantics, not in summary construction.

### 5. Failure-locality accounting is now useful

The new failure-locality definition follows changed child inputs and changed published summaries rather than recomputing one universal oracle summary. This is aligned with the architecture hypothesis.

The absence of propagation timing and control-message modeling remains acceptable for now. We are measuring information dependency and blast radius, not convergence time.

### 6. State ownership remains an experiment axis, not an invariant

The current model replicates ancestor-scope information to every physical node that consumes it. This is a defensible distributed baseline.

Do not replace it yet with scope controllers or centralized path servers, because that would change both failure semantics and state distribution. Such ownership models can be compared later as a separate axis.

## Architectural implication

The important new distinction is:

- **summary construction** asks what a scope publishes;
- **forwarding knowledge** asks what a particular forwarding node can actually use at decision time;
- **path oracle** may ask remote scopes questions that ordinary forwarding cannot.

These must no longer share one API implicitly.

A physically valid route is not sufficient evidence that the route was computable from the declared local information.

## What should not change yet

Do not optimize decomposition yet.

Do not add Endpoint ID, Rendezvous, Channel, transport, congestion, security, wireless, packet timing, or wire format.

Do not interpret S2(k=1) or S3 shortest-path recovery as proof that sparse/full boundary summaries solve routing.

Do not remove the recursive oracle implementation; retain it as an explicit upper bound for comparison.

## Next step

Implement `docs/phase3-forwarding-semantics.md` before changing decomposition. Phase 3 should compare the current recursive oracle with a knowledge-disciplined distributed forwarding model in which each decision may consume only state logically available at the current node plus the destination Locator.
