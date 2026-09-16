# Phase 3.2: Scoped Potential Routing

> Status: implementation target after Phase 3.1.
>
> This phase adds no new naming, transport, security, mobility, or destination-attachment mechanism. It replaces independently chosen per-node routes with an explicit converged progress invariant.

## 1. Core question

Can Structured Locator forwarding achieve loop-free static delivery using only scoped per-prefix progress state, without globally replicated topology or hidden remote path queries?

## 2. Potential definition

For every non-leaf Scope `S` and every immediate child prefix `P` of `S`, define a converged potential for nodes in `S`:

```text
phi[S,P](u)
```

with these semantics:

- nodes already inside target child `P` are sinks at potential 0 for this resolution;
- every other reachable node has finite positive potential;
- at least one physical neighbor inside `S` has strictly smaller potential;
- every eligible forwarding edge satisfies strict descent.

For positive weighted links, a shortest-distance fixed point is a valid control:

```text
phi(u) = min_neighbor(link_cost(u,v) + phi(v))
```

but the architecture depends only on well-founded descent, not on exact shortest-path optimality.

## 3. Locator resolution

For destination Locator `D`, node `u` identifies the first unmatched child component at the lowest common ancestor resolution.

While forwarding toward that child prefix, next hops must strictly decrease the corresponding scoped potential.

After entering the target child, resolution advances and forwarding switches to the potential for the next Locator component.

Conceptually the progress order is lexicographic:

```text
more matched Locator components is better;
while match depth is unchanged, phi must strictly decrease.
```

## 4. Eligible next hops, not one fundamental route

The architectural forwarding object should be a set:

```text
Eligible[S,P,u] = { v in physical_neighbors(u) | phi[S,P](v) < phi[S,P](u) }
```

A deterministic single successor may be selected in experiments for reproducibility, but it is not the architecture invariant.

Report eligible-set size. Later scheduling or congestion work may choose among eligible successors without changing routing correctness.

## 5. Control-plane knowledge boundary

Do not compute potentials by giving each node or the forwarding compiler the complete physical graph.

Model a converged scoped neighbor-exchange process or an equivalent fixed-point computation whose inputs are only:

- the node's direct physical neighbors and link costs;
- the node's own Structured Locator;
- the target child prefix for the current Scope;
- neighbors' advertised potential values for that same scoped prefix.

The simulator may iterate centrally to reach the fixed point, but each update must be expressible as a local neighbor operation. No update may inspect non-neighbor topology.

Charge persistent potential/control records to their owners.

## 6. State expectation

With hierarchy depth `d` and Scope fanout `f`, a node needs potential/FIB state only for child prefixes relevant along its ancestor lineage.

For the current binary control hierarchy this should remain on the order of hierarchy depth per node, plus local-leaf destination state.

Do not claim asymptotic bounds from experiments; measure actual state.

## 7. Relationship to R0

Keep R0 as the explicit boundary-reachability summary control.

Compare at least:

1. current R0 personalized-view compiled forwarding;
2. new scoped-potential forwarding;
3. Flat shortest-path baseline.

Do not force the potential implementation to consume R0 summaries if direct scoped neighbor propagation is sufficient. If R0 becomes unnecessary for forwarding under the potential model, report that clearly rather than retaining it artificially.

## 8. Static correctness target

For an initially connected graph whose fixed Scope hierarchy remains internally connected at every Scope, converged scoped-potential forwarding should satisfy:

- zero loops;
- zero false `no_route`;
- zero Hop-Budget exhaustion with a sufficiently large budget;
- only physical adjacent next hops;
- eventual entry into each required destination child prefix and final delivery inside the leaf.

Test this exhaustively on small graphs and sampled larger graphs.

## 9. Failure boundary

Do not solve scope-breaking failure detours in this phase.

Classify failures into:

- hierarchy remains Scope-connected after convergence;
- one or more fixed Scopes become internally disconnected while the physical graph remains connected;
- physical graph partitions.

Require the static correctness target after reconvergence only for the first class.

For the second class, measure failures but do not hide them with global fallback. These cases require destination/component attachment or another explicit repair mechanism later.

## 10. Metrics

Report:

- delivered / no-route / loop / budget-exhausted counts;
- weighted and hop stretch;
- potential-state normalized size;
- forwarding-state size;
- eligible-next-hop count distribution;
- changed potential/FIB objects after failures;
- number/fraction of nodes whose potential changes;
- Scope levels reached by changed control state;
- comparison against current R0 forwarding and Flat.

Include unit, weighted, relabeled, and fixed-structure relabel controls.

## 11. Important negative controls

Do not:

- use full-topology Dijkstra to synthesize potentials;
- repair loops after the fact using executor knowledge;
- add destination-to-boundary attachment hints;
- change decomposition/fanout;
- dynamically renumber locators;
- add centralized path servers;
- model transient convergence yet.

This phase studies the converged fixed point only.

## 12. Exit criteria

Phase 3.2 is complete when experiments answer:

1. Does an explicit scoped potential eliminate stable loops on every Scope-connected static test instance?
2. Can it preserve reachability with less state than Flat full-topology knowledge?
3. What stretch results from choosing only progress-safe successors?
4. How much control/FIB state changes after a local failure that preserves Scope connectivity?
5. Does R0 remain architecturally useful once scoped scalar potentials exist, or is it mainly a validation/compression reference?

Only after this should the project address failures that break Scope connectivity or add destination-attachment lookahead.
