# Phase 5: Metric-Aware Scope Decomposition

> Status: implementation specification after Phase-4 review.
>
> Phase 5 does not change packet semantics, attachment lookahead, potentials, or prefix-monotone forwarding. It varies only Scope decomposition.

## 1. Core research question

Can topology compression choose Scopes that are simultaneously:

- low-boundary enough to save routing/control state;
- approximately isometric enough to avoid hierarchy stretch;
- stable enough to remain meaningful under modest topology changes?

The existing balanced connected bisection remains a control, not the candidate decomposition.

## 2. Primary decomposition metric: scope distortion

For every Scope `S`, compare internal and global physical distance:

```text
escape_ratio_S(u,v) =
    d_G[S](u,v) / d_G(u,v)
```

for `u,v in S`.

Report per Scope and aggregated by depth:

- pair count;
- mean;
- p50/p95/p99/max;
- exactly-one fraction.

Also report the worst Scope and the pair causing its maximum distortion when practical.

Weighted experiments must use weighted link cost.

## 3. Boundary/compression metrics

For every Scope report at least:

- member count;
- boundary-interface count;
- crossing-link count;
- boundary/member ratio;
- child count;
- depth.

At decomposition level also report the resulting state of:

- h=1;
- h=2;
- h=3;
- full;
- Flat reference.

Do not hide boundary complexity behind one composite score.

## 4. Decomposition strategies

Implement decomposition behind the existing interchangeable interface.

At minimum compare:

### D0 — current balanced connected bisection

Keep unchanged as the historical control.

### D1 — metric-aware low-distortion decomposition

Add an experimental strategy that explicitly considers weighted metric distortion when choosing connected splits.

The exact optimization algorithm is an implementation detail, but it must expose its objective inputs and parameters.

For small graphs it is acceptable to use expensive global-distance calculations as a decomposition-research oracle. Label it clearly as such; do not imply that the formation algorithm is already scalable or distributed.

Its goal is to find a better state/distortion point, not to prove a deployable clustering protocol.

### Dbad — deliberately poor connected decomposition

Include a deterministic/random bad-partition control where practical. This is important to verify that the new metrics actually predict hierarchy stretch.

### Topology-native control

For generator families with an obvious structural decomposition that can be produced without hand-tuning individual graph instances, optionally include a generator-native hierarchy.

Examples may include tree subtrees or rectangular mesh regions.

Keep it as a control, not privileged truth.

## 5. Do not optimize one hidden scalar only

The research output should remain multi-objective.

Primary axes:

```text
boundary/state
scope distortion
full-lookahead hierarchy stretch
finite-lookahead total stretch
churn/failure locality
```

An internal search algorithm may use a tunable score, but experiments must report the underlying terms separately and sweep the tradeoff parameter where relevant.

## 6. Key hypothesis to test

Phase 4 suggests:

```text
low scope distortion
    -> low full-lookahead hierarchy stretch
```

Phase 5 must test this directly across topology families and weighted variants.

Report correlations between decomposition-level distortion summaries and observed `full / Flat` hierarchy stretch.

Do not assume correlation implies a complete causal model; the exact isometry criterion is the zero-distortion endpoint.

## 7. Experiment matrix

Use the same physical graph instance when comparing decompositions.

At minimum include:

- tree;
- mesh/torus;
- Erdos-Renyi;
- expander-like;
- unit cost;
- skewed weighted cost;
- multiple seeds;
- fixed graph labels for paired comparison.

For small graphs use exhaustive source/destination pairs.

For each decomposition run at least:

```text
h=1
h=2
h=3
full
Flat
```

The most important route metric for decomposition selection is `full / Flat`, because it removes limited-lookahead information error.

## 8. Correctness invariants

Changing decomposition must not weaken the established forwarding semantics.

For every candidate hierarchy used in a correctness experiment:

- every leaf Scope is connected initially;
- Locator construction is valid;
- all static pairs deliver;
- eligible next hops are physical;
- potentials strictly decrease within active resolution;
- no stable loops;
- full-lookahead cost is never below Flat.

If a candidate decomposition produces disconnected Scopes, reject it rather than repairing forwarding with global knowledge.

## 9. State accounting

Charge state exactly as in Phase 4.

Decomposition metadata or simulator search working memory is not forwarding architecture state.

However, record decomposition construction cost separately where feasible:

- number of candidate splits evaluated;
- shortest-path computations or equivalent work;
- wall-independent operation counters if practical.

This is research-algorithm cost, not data-plane state.

## 10. Failure experiments

Keep failure handling semantics unchanged.

Measure whether different decompositions alter:

- probability that a physical failure breaks an induced Scope;
- changed potential/attachment objects;
- affected node fraction;
- highest Scope level reached.

This matters because a geometrically excellent but fragile Scope may be a poor architecture choice.

Do not add dynamic Scope restructuring yet.

## 11. Scaling

After small-graph correctness:

- retain 16/32/64/128 modest scaling;
- compare state and hierarchy stretch for D0 and the most promising D1 parameter points;
- do not make asymptotic claims.

If the metric-aware search is too expensive at 128 nodes, report that limitation rather than weakening its semantics silently.

## 12. Phase-5 decision rule

After Phase 5, choose the next architecture branch from evidence:

### If a better decomposition makes full hierarchy stretch near 1 with useful state savings

Keep prefix-monotone forwarding and proceed toward scalable Scope formation / dynamic control-plane semantics.

### If hierarchy stretch remains large even for low-distortion, carefully optimized partitions

Derive controlled Scope escape or another relaxation of prefix monotonicity.

### If good partitions exist but require boundary/state comparable to Flat

Treat that as evidence that those topology families are fundamentally poor candidates for hierarchical compression.

## 13. Non-goals

Do not yet:

- permit Scope escape;
- change Locator format;
- add packet path state;
- alter potential/eligible-next-hop semantics;
- add Endpoint ID/Rendezvous/Channel;
- model asynchronous convergence;
- dynamically restructure ScopeTree after failures;
- claim the metric-aware decomposition algorithm is deployable at global scale.

## 14. Phase-5 exit criteria

Phase 5 is complete when we can answer:

1. How strongly does Scope metric distortion predict hierarchy stretch?
2. How much can metric-aware decomposition reduce full-lookahead stretch relative to balanced bisection?
3. What boundary/state price is paid for that reduction?
4. Which topology families admit large, low-boundary, approximately isometric Scopes?
5. Which families appear intrinsically hostile to laminar compression?
6. Does the evidence justify keeping prefix-monotone routing, or is controlled Scope escape the next necessary mechanism?
