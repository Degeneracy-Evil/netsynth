# Phase 2: Routing Summary Information Budget

> Status: implementation specification after Phase-1 review.
>
> Phase 2 does not add new network features. It tests how much topology information a compressed routing architecture must retain to obtain useful path quality while preserving state and failure-locality benefits.

## 1. Phase-1 conclusion

Phase 1 established that the simulator can reproduce both favorable and hostile cases. The current recursive routing model is intentionally weak: quotient edges are weighted only by the cheapest physical crossing link, and the router then chooses the cheapest crossing edge without charging or using the internal cost required to reach that boundary.

The observed stretch on mesh, irregular random, and expander-like graphs therefore does **not** yet falsify recursive topology compression. It demonstrates that adjacency-only / minimum-crossing information is insufficient for high-quality path selection on those graphs.

Phase 1 also exposed a metric inconsistency that must be fixed before architectural conclusions are drawn:

- compressed routing uses one information model;
- failure-locality computation uses a stronger boundary summary (crossing links plus exact boundary-to-boundary distances);
- routing-state and churn metrics do not charge that stronger summary.

Phase 2 must make the information model explicit and charge every routing summary that a strategy consumes.

## 2. Core research question

For each topology family, what is the Pareto frontier between:

1. routing/control state;
2. path stretch;
3. churn after topology changes;
4. failure locality?

The target is not necessarily stretch = 1. The useful result is whether a clear Pareto knee exists: a relatively small amount of summarized state that captures most of the path-quality benefit of full topology knowledge.

## 3. Information-budget principle

A routing strategy may only use information that is represented in its declared summary model, and all persistent information it uses must be included in state accounting.

Do not let routing use hidden access to the physical graph except where the model explicitly grants local detailed knowledge.

Metrics must distinguish at least:

- **data-plane forwarding state**: entries required for forwarding decisions;
- **local detailed topology state**: full-resolution topology legitimately retained inside a node's local scope;
- **remote summary state**: quotient edges, portal/boundary records, landmark information, or other compressed remote knowledge;
- **auxiliary control state**: persistent routing objects required by the strategy.

Report these categories separately. A combined total may also be reported, but do not hide category differences behind one scalar count.

## 4. Summary strategies

Implement each strategy behind an interchangeable interface. Exact names are implementation details; the semantic levels below matter.

### S0 — Adjacency-only quotient

This is the Phase-1 conservative model.

A parent scope knows that child scopes are adjacent and knows crossing-link cost metadata, but it does not know the internal cost of reaching a particular crossing boundary.

Purpose: lower-information baseline.

### S1 — Boundary-bundle summary

Group crossing links between the same pair of sibling scopes into boundary bundles. Expose limited aggregate information sufficient to distinguish materially different exits without publishing a complete boundary matrix.

At minimum experiment with aggregate crossing cost and a small number of representative portals/bundles.

Purpose: determine whether modest portal awareness removes most of the Phase-1 stretch.

### S2 — Landmark / sparse-portal summary

Select a bounded number `k` of representative boundary/portal nodes per scope. Publish distances among those representatives and enough attachment information to estimate access/egress cost.

`k` must be an experiment parameter and its state cost must be charged.

Purpose: produce an explicit information-budget curve rather than a single hand-picked summary.

### S3 — Full boundary distance summary

Publish exact distances among stable boundary nodes together with crossing information.

This is an intentionally expensive upper compressed baseline and may require O(B^2) state for B boundary nodes.

Purpose: distinguish losses caused by topology decomposition itself from losses caused merely by an overly weak summary.

### Flat — Full topology baseline

Continue using globally informed shortest-path routing as the path-quality reference.

Do not interpret it as a deployable architecture at large scale; it is a baseline.

## 5. Decomposition control

Keep the current balanced connected decomposition as one fixed control so Phase 2 can isolate the effect of summary strength.

Do **not** simultaneously optimize decomposition and summary in the first Phase-2 experiments. Otherwise an improvement cannot be attributed cleanly.

After summary experiments are stable, add decomposition strategies separately, including at least:

- current balanced connected bisection;
- topology-native/manual hierarchy for generators where a natural hierarchy exists;
- separator/community-oriented partitioning;
- deliberately poor/random connected partitioning as a control.

## 6. State accounting

The current entry-only state metric is insufficient for architecture comparison.

For every strategy, report per-node and network-total counts for each state category. Where objects have materially different size, also report a deterministic normalized size estimate rather than pretending one object always equals one unit.

At minimum include:

- forwarding entries;
- detailed topology nodes/links retained;
- quotient adjacency objects;
- crossing-link or boundary-bundle objects;
- portal/landmark records;
- boundary/landmark distance records;
- any persistent lookup/index state required by the routing model if it scales with topology size.

Implementation-language containers, Python object overhead, caches used only to accelerate the simulator, and transient Dijkstra working memory are not architecture state.

## 7. Churn accounting

A topology event must measure changes in all persistent architectural state consumed by the strategy, not only forwarding entries.

Report separately:

- changed forwarding objects;
- changed local detailed-topology objects;
- changed remote-summary objects;
- number/fraction of nodes that must receive changed information;
- highest scope level reached.

Do not equate local recomputation CPU work with propagated control traffic.

## 8. Failure locality

Failure locality must be evaluated using the same summary strategy that routing uses.

A failure has escaped a scope only when that scope's externally published summary under the chosen strategy changes. It then reaches the parent because the parent consumes that summary. Propagation continues only if the parent's own externally published summary changes.

Do not use the full boundary-distance summary to judge locality for an S0/S1/S2 routing strategy unless it is being reported as a separate oracle metric.

## 9. Path quality

Continue to report mean, p50, p95, p99, max, exact-shortest fraction, compressed route failures, and invalid routes.

Add, where useful:

- additive path overhead;
- hop-count stretch separately from weighted-cost stretch when weighted links are used;
- results grouped by source/destination hierarchy relationship (same leaf scope, sibling scopes, distant scopes).

The grouped results are important for identifying where abstraction loses information.

## 10. Topology families and scale

Retain structurally diverse families:

- tree / hierarchical;
- Clos-like;
- mesh and torus;
- random geometric;
- small-world;
- Erdos-Renyi;
- expander-like.

Correctness and exhaustive validation remain more important than very large node counts. Use small-to-medium graphs first. Do not optimize for 10^4+ nodes until metric semantics and strategy comparisons are stable.

## 11. Required experiment matrix

For each selected graph instance, keep the physical topology and decomposition fixed and run:

`Flat, S0, S1, S2(k1), S2(k2), ..., S3`

with identical source/destination samples and failure events.

This produces a direct information-budget curve instead of comparing unrelated runs.

## 12. Phase-2 exit criteria

Phase 2 is complete when reproducible experiments can answer:

1. How much of Phase-1 stretch comes from weak summaries versus the hierarchy/decomposition itself?
2. Does a Pareto knee exist between summary state and path stretch for each graph family?
3. Which graph families remain hostile even with strong summaries?
4. How much state and failure propagation does each summary strength require?
5. Is the current laminar recursive-compression hypothesis still promising enough to continue, or should it be weakened/replaced?

A negative answer is a valid result. Do not tune the simulator merely to preserve the current architecture hypothesis.
