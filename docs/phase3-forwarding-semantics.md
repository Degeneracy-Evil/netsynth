# Phase 3: Knowledge-Disciplined Forwarding

> Status: implementation specification after Phase-2 review.
>
> Phase 3 does not optimize scope decomposition and does not add transport/network features. It closes the gap between a physically valid recursively computed path and a path that can actually be chosen from information available to the current forwarder.

## 1. Core research question

Given the same ScopeTree and S0/S1/S2/S3 summaries, what path quality remains when every forwarding decision is restricted to information that the current node is logically allowed to know?

Phase 2's recursive route constructor is retained as an **oracle upper bound**. It must no longer be treated as the deployable compressed-routing result.

## 2. Critical distinction

Keep these three concepts separate:

1. **Published summary** — what a scope exposes upward.
2. **Per-node forwarding knowledge** — what one physical forwarder stores/consumes.
3. **Recursive path oracle** — a simulator mechanism that may ask remote child scopes for exact subpaths.

Only (1) and (2) define the candidate architecture. (3) is a comparison bound.

A route being physically valid is not enough. The simulator must be able to show that each next-hop decision was derivable from the current node's declared knowledge.

## 3. Minimal Structured Locator model

Phase 3 should stop using hidden global target-membership lookup as part of forwarding.

Introduce a minimal topology-derived Locator representation. Conceptually:

```text
<scope-component, scope-component, ..., leaf-local-selector>
```

The exact wire encoding remains out of scope.

Requirements:

- `ScopeTree` can derive a Locator for a physical forwarding node;
- a packet/route request supplies the destination Locator explicitly;
- the current forwarder may compare the destination Locator with its own lineage to determine relevant target child scopes;
- portal/crossing references that require routing to a particular boundary must contain enough locator/reference information to identify that boundary without a hidden global `node -> scope lineage` query;
- report locator-depth/component statistics separately; do not invent a fixed 128/256-bit encoding yet.

Do **not** introduce Endpoint ID or Rendezvous. This Locator names topology position only.

## 4. Per-node knowledge object

Construct an explicit immutable `ForwardingKnowledge(owner)` (name is implementation-defined) from charged architectural state.

It may contain only information logically owned by that node, including:

- detailed topology of the owner's finest local scope;
- summaries and crossing/quotient information legitimately consumed along the owner's ancestor scopes;
- the owner's own locator/lineage;
- explicit locator/reference data carried by those summary objects.

It must not expose:

- the full physical graph;
- exact detailed topology of remote leaf scopes;
- arbitrary `ScopeTree.leaf_for(target)` / lineage queries for remote targets not derived from the supplied Locator;
- a callable route planner inside a remote child;
- uncharged destination-specific distances.

Prefer making violations impossible by API/type structure rather than relying only on comments.

## 5. Distributed next-hop execution

Add a routing mode that advances one physical hop (or one explicitly local detailed segment whose first hop is derived locally) at a time.

Conceptually:

```text
next_hop(current_node, destination_locator, knowledge[current_node]) -> physical_neighbor | failure
```

A separate simulator/executor may use the physical graph only to:

- verify the chosen next hop is currently adjacent;
- accumulate actual path cost/hops;
- apply failures;
- terminate on destination, failure, loop, or Hop Budget exhaustion.

The routing decision itself must not access the physical graph except through knowledge explicitly granted to the current node.

Record loops and Hop-Budget exhaustion separately from ordinary no-route failures.

## 6. Scope transition rule

The exact heuristic is an experiment strategy, but it must obey the knowledge boundary.

A reasonable first control is:

1. if destination is inside the current node's detailed local scope, choose the local shortest-path next hop;
2. otherwise use the destination Locator to identify the relevant target aggregate at ancestor resolution;
3. use only locally owned summary/crossing information to choose an exit/portal toward that aggregate;
4. route locally toward that selected boundary;
5. after crossing into another scope, let the new current node make the next decision from its own knowledge.

Do not let a parent/source node ask the target child for exact `interface -> target` cost merely to choose the globally best ingress.

If a summary does not contain enough information to distinguish ingress choices, use a deterministic local policy and accept the resulting stretch. That is the information-budget tradeoff we are trying to measure.

## 7. Destination-specific information must be explicit

If an experiment wants to improve target ingress selection using information about the final destination, model that as a separate strategy and charge it.

Possible later strategies include:

- destination-to-portal attachment hints carried in the Locator;
- destination-specific aggregate forwarding state;
- on-demand remote path-query/control mechanisms.

None is part of the initial Phase-3 candidate.

This distinction is important because exact boundary-to-boundary metrics alone do not imply exact boundary-to-arbitrary-interior-destination metrics.

## 8. Preserve the oracle as an upper bound

Keep the Phase-2 recursive overlay router under an explicit name such as `recursive_oracle`.

For every summary strategy, compare:

```text
Flat shortest path
Recursive oracle using that summary
Knowledge-disciplined distributed forwarding using that summary
```

The gap between oracle and distributed forwarding is itself a metric. It quantifies how much apparent path quality depended on hidden remote path queries rather than the published information budget.

## 9. Summary strategy interpretation

Do not treat S0/S1/S2/S3 as a strictly monotonic ladder in total state.

In particular, S1 may use less state than S0 because it replaces many raw crossing objects with compressed boundary bundles while publishing more useful derived information.

Treat every strategy as a point in the multidimensional design space:

```text
state representation
path quality
churn
failure locality
```

## 10. Stronger experiment controls

Before decomposition optimization, strengthen correctness experiments.

### Exhaustive pairs

For small graphs, use all ordered source/destination pairs rather than samples.

### Multiple seeds / instances

Run multiple graph instances per family. Do not draw conclusions from one generated graph.

### Weighted costs

Add deterministic weighted-link variants, including nonuniform/skewed costs. Unit-hop graphs can hide poor ingress choices.

### Label sensitivity

Current decomposition/portal/landmark controls use deterministic node ordering in several tie-breaks. Add graph relabeling/permutation experiments or equivalent checks so results that depend heavily on arbitrary node IDs are visible.

Do not silently make the algorithm topology-aware merely to improve results; report label sensitivity first.

### S2 landmark counts

Retain `k=1,2,4,...`, but do not expect monotonic improvement. Report when additional landmarks add state without reducing distributed-forwarding stretch.

## 11. Metrics

Retain Phase-2 state, churn, and failure-locality accounting.

For path quality report separately for oracle and distributed forwarding:

- weighted stretch;
- hop stretch;
- additive overhead;
- exactly-shortest fraction;
- route failures;
- loops;
- Hop-Budget exhaustion;
- same-leaf / sibling / distant groups.

Add:

```text
oracle_gap = distributed_route_cost / oracle_route_cost
```

where both routes exist.

Also report Locator depth/component distributions.

## 12. Tests required

Add tests that make knowledge-boundary violations observable.

At minimum:

1. distributed forwarding succeeds on simple trees without global graph access;
2. no remote leaf detailed topology is present in another node's `ForwardingKnowledge`;
3. changing hidden remote interior topology without changing its published summary cannot directly change a remote node's next-hop decision before information legitimately propagates;
4. portal/boundary routing works using explicit Locator/reference data rather than global membership lookup;
5. the recursive oracle remains physically valid but is labeled separately;
6. S3 oracle shortest-path recovery is not asserted as a property of distributed forwarding;
7. loops/Hop-Budget exhaustion are surfaced, never silently repaired by a global shortest-path fallback.

## 13. What not to do

Do not optimize decomposition yet.

Do not add a centralized scope controller/path server to recover Phase-2 path quality. That is a different ownership architecture and can be studied later.

Do not add destination-specific hints merely to make S3 shortest again.

Do not use the full graph as an invisible fallback when distributed forwarding cannot decide.

Do not optimize for large graph performance until the knowledge semantics are correct.

## 14. Phase-3 exit criteria

Phase 3 is complete when we can answer:

1. How much of Phase-2 path quality survives strict per-node information boundaries?
2. How large is the oracle-vs-distributed gap for S0/S1/S2/S3 on each graph family?
3. Does a useful state/stretch Pareto knee still exist without remote path queries?
4. Which failures/loops arise because summaries lack enough information for local forwarding?
5. How sensitive are results to weighted costs, graph instances, and arbitrary node labeling?
6. Is Structured Locator + laminar Scope summary still sufficient as the routing core, or does the architecture require an explicit new mechanism for destination attachment/path discovery?

Only after these questions are answered should we optimize Scope decomposition or introduce multiway partitions.
