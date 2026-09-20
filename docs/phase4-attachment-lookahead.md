# Phase 4: Hierarchical Attachment Lookahead

> Status: implementation specification after Phase-3.2 review.
>
> Phase 4 keeps the packet format, fixed ScopeTree, prefix-monotone forwarding rule, and strict-descent potential semantics unchanged. It varies only how many levels of destination attachment information are exposed upward.

## 1. Core research question

How much path-quality improvement is obtained by exposing progressively deeper destination-prefix attachment information, and what state/churn cost does that information require?

Phase 3.2 is the lookahead-1 baseline.

## 2. Why naive deeper-prefix potentials are incorrect

Do not simply compute an unrestricted parent-Scope potential directly to a deep descendant prefix.

Such a potential may value a path that:

1. enters the target child;
2. leaves that child again;
3. later re-enters it.

The real data plane does not execute that plan. Once the packet enters the target child, Locator resolution increases and forwarding switches to the child's own scoped state.

Therefore parent-level lookahead must be compositional with the forwarding semantics actually executed.

## 3. Prefix-monotone attachment semantics

For a target prefix `P` contained in child Scope `C` of parent Scope `S`, child `C` may publish to `S` an attachment value for each relevant boundary ingress `b`:

```text
A[C,P](b) = converged cost from boundary b to prefix P
            under C's own prefix-monotone forwarding semantics
```

The parent does not learn C's internal topology.

Instead, those boundary attachment values act as terminal costs when S computes its potential toward P.

Conceptually:

```text
outside S/C
    |
    | parent potential
    v
boundary b of C
    |
    | advertised attachment cost A[C,P](b)
    v
deeper target prefix P
```

Once the packet physically crosses into C, the parent potential is no longer used. C's own forwarding state takes over.

## 4. Lookahead depth

Define `h` as the number of destination hierarchy levels resolved at the active Scope.

- `h = 1`: Phase-3.2 behavior; target is the immediate child.
- `h = 2`: ingress selection is informed by attachment to the target grandchild.
- `h = 3`: attachment to the next three hierarchy levels.
- `h = full`: attachment information is recursively resolved to the final leaf-local destination.

The packet already carries the full Structured Locator. No new packet field is introduced.

Lookahead changes control-plane information, not packet semantics.

## 5. Bottom-up construction

Lookahead information must be constructed recursively.

For `h = 1`, an immediate target child is a zero-cost sink set exactly as in Phase 3.2.

For `h > 1`:

1. the target child computes its own `h-1` attachment potentials;
2. only attachment values at its parent-visible boundary interfaces are exposed upward;
3. the parent uses those values as terminal costs;
4. ordinary nodes in the parent Scope converge potentials through neighbor advertisements;
5. all persistent attachment and potential records are charged.

No parent may inspect descendant physical topology or call a descendant route planner.

## 6. Distributed realizability

Every converged value must remain expressible using local fixed-point updates.

A parent node may use:

- its direct physical neighbors and link costs;
- neighbor advertisements for the same target prefix;
- explicit boundary attachment advertisements received from the target child.

It may not use:

- the full physical graph as routing knowledge;
- hidden node-to-Scope target lookup;
- exact descendant topology;
- uncharged destination-specific distances;
- global shortest-path fallback.

The simulator may use full topology only for validation and reference metrics.

## 7. Loop freedom

Lookahead must preserve Phase-3.2 strict-descent forwarding.

Within one active Scope, eligible next hops must strictly decrease the potential for the selected lookahead prefix.

When the packet enters the immediate target child, Locator-prefix match increases and the child takes over.

Thus the forwarding progress measure is lexicographic:

```text
(prefix resolution progress, scoped potential)
```

Resolution never goes backward, and potential strictly decreases while resolution is unchanged.

## 8. Full-lookahead reference

Implement a `full` lookahead strategy.

This is not expected to equal unrestricted Flat shortest-path routing.

It should represent the best metric routing obtainable under the current **prefix-monotone hierarchy constraint**, assuming exact recursively composable destination attachment information.

Use it as the reference:

```text
Flat shortest path
    <=
Full-lookahead prefix-monotone path
    <=
Limited-lookahead path
```

when all compared routes exist.

If implementation details violate this ordering, investigate rather than assuming the hierarchy model is at fault.

## 9. Decompose stretch

Report two separate ratios whenever possible.

### Hierarchy stretch

```text
hierarchy_stretch =
    full_lookahead_cost / flat_shortest_cost
```

This measures loss caused by prefix-monotone hierarchy itself.

### Information stretch

```text
information_stretch(h) =
    lookahead_h_cost / full_lookahead_cost
```

This measures loss caused by limited destination attachment resolution.

The ordinary end-to-end stretch remains:

```text
total_stretch(h) =
    lookahead_h_cost / flat_shortest_cost
```

This decomposition is a primary Phase-4 output.

## 10. State accounting

Charge at least:

- own Locator;
- direct-neighbor link state;
- potential records;
- eligible-next-hop records;
- boundary attachment advertisements;
- any prefix identifiers needed to key those records.

Do not charge transient Bellman work or simulator caches.

Report state by lookahead level and semantic category.

For a balanced hierarchy, expect state to grow rapidly with lookahead. Measure it; do not assert an asymptotic law from small experiments.

## 11. Churn

A deeper target attachment can cause an internal metric change to propagate farther upward even when reachability is unchanged.

For each lookahead level report:

- changed potential records;
- changed attachment advertisements;
- changed eligible-next-hop objects;
- changed nodes/fraction;
- highest Scope level reached.

This propagation cost is part of the information-quality tradeoff, not an implementation nuisance.

## 12. Experiment matrix

Keep the decomposition fixed.

At minimum compare:

```text
h = 1
h = 2
h = 3
h = full
Flat
```

Use:

- tree;
- mesh/torus;
- Erdos-Renyi;
- expander-like;
- unit and skewed weighted costs;
- multiple seeds;
- fixed-structure relabel controls.

Small graphs should use exhaustive ordered pairs.

Retain modest scaling only after correctness is established.

## 13. Required correctness tests

At minimum verify:

1. `h=1` reproduces Phase-3.2 forwarding semantics;
2. every attachment advertisement is derivable bottom-up without descendant topology access;
3. every eligible next hop is physical and strictly decreases the selected potential;
4. all static pairs deliver when every Scope is connected;
5. scope-connected converged failures remain loop-free and deliver;
6. no new packet field is required;
7. full lookahead never relies on unrestricted leave-and-reenter paths;
8. full-lookahead cost is never below Flat shortest-path cost;
9. limited-lookahead cost is never below the corresponding full-lookahead prefix-monotone reference because of hidden information.

## 14. Non-goals

Do not yet:

- change decomposition or fanout;
- allow leaving a target Scope after entering it;
- repair scope-breaking failures;
- add Endpoint ID/Rendezvous/Channel;
- model asynchronous convergence;
- add a path server or centralized controller;
- change the packet Locator format;
- optimize large-scale runtime.

## 15. Phase-4 exit criteria

Phase 4 is complete when experiments can answer:

1. How much of current stretch is caused by coarse destination attachment information?
2. How much remains even with full attachment because of prefix-monotone hierarchy?
3. Is there a useful state/stretch Pareto knee at small lookahead such as `h=2` or `h=3`?
4. How quickly do state and churn grow with attachment depth?
5. On which topology families does full lookahead still perform badly?
6. Should the next architecture step optimize decomposition, permit controlled Scope escape, or keep the current hierarchy and move on to dynamic-control-plane semantics?
