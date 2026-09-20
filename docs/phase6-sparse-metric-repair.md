# Phase 6: Sparse Metric Repair

> Status: implementation specification after Phase-5 review.
>
> Phase 6 keeps Structured Locators, scoped potentials, attachment lookahead, and ordinary prefix-monotone forwarding. It adds sparse, explicit boundary-to-boundary escape shortcuts as exceptions for non-isometric Scopes.

## 1. Core research question

Can a small number of explicit external shortcuts repair most hierarchy distortion more cheaply than making the entire ScopeTree nearly isometric?

The main comparison is:

```text
D0 + sparse shortcuts
D1 + no shortcuts
Flat
```

D0 remains the primary decomposition so shortcut effects are isolated.

## 2. External shortcut definition

For a non-root Scope `S` with boundary interfaces `B(S)`, an external shortcut is a directed logical edge:

```text
X = (S, exit=a, reentry=b, escape-domain A)
```

where `a,b in B(S)`.

Its logical cost is the shortest physical path from `a` to `b` in an explicitly declared escape domain that permits leaving `S`.

The shortcut is control-plane state. It is never a physical next hop.

## 3. Escape domains

Implement at least two research modes.

### Parent-local

The escape domain is the parent Scope, with the interior of `S` excluded except for boundary interfaces.

This preserves locality and is the main candidate mechanism.

### External-closure oracle

Allow the escape path to use the full physical graph with the interior of `S` excluded except for its boundary.

This is a research upper bound that measures how much distortion could be repaired by arbitrary external detours.

Do not present the external-closure oracle as deployable.

## 4. Exact closure reference

If every useful boundary pair is represented by its external-closure distance, then any physical path that leaves and re-enters `S` can be represented as alternating:

```text
internal segment
external shortcut
internal segment
...
```

Thus the all-pairs external closure is the reference for eliminating Scope distortion without changing membership.

Report its shortcut count and state explicitly; it may be quadratic in boundary size.

## 5. Sparse shortcut budgets

For the main candidate, sweep a bounded shortcut budget per Scope, for example:

```text
k = 0, 1, 2, 4
```

where `k=0` reproduces the no-escape baseline.

For small graphs, a greedy global-distance research algorithm may select shortcuts by the reduction they produce in augmented Scope distortion.

Record the selection work separately.

Do not claim the selector is deployable.

Also include the all-beneficial/all-pairs closure oracle where tractable.

## 6. Augmented Scope metric

Normal destination forwarding should compute potentials over:

```text
physical edges inside S
+
selected virtual shortcut edges
```

A virtual edge may become an eligible action only when it strictly decreases the same destination/prefix potential used by ordinary forwarding.

This is important: shortcuts are part of the same value function, not an ad-hoc exception chosen independently.

## 7. Transit context

Add one optional temporary packet forwarding context.

Conceptually:

```text
Packet {
    Destination Locator
    Hop Budget
    Transit Shortcut ID?   // absent in normal mode
}
```

The shortcut identifier is Scope-local / anchor-local; exact wire encoding remains out of scope.

Normal packets carry no shortcut context.

When a node selects a virtual shortcut:

1. it activates that shortcut ID;
2. forwarding temporarily follows the shortcut's own strict-descent physical potential;
3. nested shortcut activation is forbidden while a transit context is active;
4. when the re-entry boundary is reached, the context is cleared;
5. normal destination forwarding resumes.

Only one transit slot is required.

## 8. Shortcut realization

Each shortcut must be realizable hop-by-hop without hidden path lookup.

Compile a shortcut-specific physical potential over its declared escape domain toward the re-entry boundary.

Eligible transit next hops must:

- be physical neighbors;
- remain inside the escape domain;
- strictly decrease the shortcut potential.

The simulator may use global shortest paths only to construct the research oracle/selector and to validate reference quality, not in data-plane forwarding.

Charge shortcut realization state explicitly.

## 9. Loop-freedom invariant

For a normal destination key `K`, let `V_K` be the augmented Scope potential.

A shortcut `a -> b` may be activated only if:

```text
V_K(a) = shortcut_cost(a,b) + V_K(b)
```

up to deterministic tie rules, and the transition gives strict progress for positive-cost networks.

During transit, the shortcut-specific potential strictly decreases until `b`.

After completion:

```text
V_K(b) < V_K(a)
```

so normal forwarding cannot return to the same pre-shortcut state while respecting strict descent.

Tests must verify zero stable loops.

## 10. State accounting

Charge at least:

- shortcut metadata;
- shortcut IDs/references;
- shortcut-specific potential records;
- transit eligible-next-hop records;
- normal augmented potential/eligible state;
- attachment state for the chosen lookahead;
- Locator and direct-neighbor state.

Report packet-state overhead separately as structural components:

- fraction of delivered routes that activate a shortcut;
- shortcut activations per route;
- maximum simultaneously active transit contexts (must be 1).

Do not invent a fixed bit width yet.

## 11. Metrics

For each shortcut budget report:

- total weighted stretch;
- hierarchy stretch under full lookahead;
- state;
- augmented Scope distortion;
- shortcut count;
- boundary pairs repaired;
- shortcut-use fraction;
- activations per delivered route;
- failure churn;
- affected-node fraction.

Also estimate a greedy metric-repair curve:

```text
shortcut count -> Scope distortion
```

This is a practical approximation to `R_epsilon(S)`.

## 12. Experiment matrix

Use the same physical graph when comparing all mechanisms.

At minimum:

- D0, no shortcuts;
- D0 + parent-local k=1;
- D0 + parent-local k=2;
- D0 + parent-local k=4;
- D0 + external-closure oracle where tractable;
- D1, no shortcuts;
- Flat.

For forwarding quality use:

- `h=3` as the practical finite-lookahead candidate;
- `full` as the clean hierarchy/escape reference.

Use tree, mesh/torus, Erdos-Renyi, and expander-like graphs with unit and skewed weighted costs, multiple seeds, and paired labels.

## 13. Failure experiments

This mechanism may also repair Scope-breaking failures.

For converged failures, report:

- physically reachable pairs;
- pairs delivered without shortcut repair;
- additional pairs recovered by shortcuts;
- remaining no-route;
- loops;
- shortcut invalidations;
- changed shortcut potentials/state.

Do not dynamically restructure the ScopeTree.

## 14. Correctness tests

At minimum verify:

1. `k=0` exactly reproduces the no-escape forwarding baseline;
2. every virtual shortcut maps to a real physical escape path;
3. transit forwarding never uses a non-adjacent hop;
4. shortcut potentials strictly decrease;
5. nested shortcuts never occur;
6. transit context is cleared exactly at the declared re-entry boundary;
7. normal augmented potentials strictly decrease across physical and virtual actions;
8. all static connected pairs deliver;
9. zero stable loops;
10. external-closure reference never beats Flat shortest-path cost;
11. adding the complete external boundary closure reproduces unrestricted Scope metric on small correctness graphs.

## 15. Non-goals

Do not yet:

- allow unconstrained arbitrary Scope escape;
- dynamically change Scope membership;
- add multi-shortcut stacks;
- add source routing;
- change the destination Locator format;
- add Endpoint ID/Rendezvous/Channel;
- model asynchronous/stale control updates;
- claim the shortcut selector is scalable or distributed.

## 16. Phase-6 exit criteria

Phase 6 is complete when we can answer:

1. How many external shortcuts are needed to remove most Scope distortion?
2. Does D0 + sparse repair dominate D1 in state/stretch on random and expander-like graphs?
3. How much packet transit context is actually exercised?
4. Can the same mechanism repair a useful fraction of Scope-breaking failures?
5. Which topology families have low versus high metric-repair complexity?
6. Is a prefix-monotone core plus sparse explicit exceptions a viable general architecture, or do hostile graphs still require essentially Flat information?
