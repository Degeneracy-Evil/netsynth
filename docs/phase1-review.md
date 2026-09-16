# Phase 1 Architecture Review

> Reviewed implementation: `118d28c62fe67ec3e21e4d5edc15744e1efd32e8`
>
> Result: Phase 1 is useful and should be kept. Its negative results are informative, but several metrics currently use different information models and therefore must not yet be interpreted as one architecture Pareto comparison.

## What Phase 1 established

The simulator has the right research shape: the physical graph, decomposition, routing strategy, failure events, metrics, and reproducible experiment output are separated cleanly. The implementation also preserves the intended non-goals and does not introduce TCP/IP-specific assumptions.

The current results are valuable precisely because they are unfavorable on several non-tree topologies. They show that the weakest recursive summary/routing policy does not preserve path quality well outside favorable hierarchical graphs.

## Main findings

### 1. Phase-1 stretch measures weak portal selection, not only decomposition quality

`CompressedRouting` constructs quotient edges using the minimum physical crossing-link cost. It then selects the cheapest physical crossing edge for the chosen sibling transition, without considering the cost required to reach that boundary or the downstream cost after entering the next scope.

Therefore the observed stretch on mesh, random, and expander-like graphs should currently be interpreted as:

> minimum-crossing / adjacency-level summaries are insufficient for good path selection.

It does not yet show that recursive topology compression itself is unsound.

### 2. The current binary decomposition makes quotient routing almost trivial

`BalancedConnectedDecomposition` recursively creates exactly two children per non-leaf scope. Consequently each quotient graph contains only two child vertices. For a connected parent scope there is necessarily at least one crossing edge between them, so there is no interesting multi-hop sibling-level route choice inside that quotient.

Phase 1 therefore primarily measures the cost of recursively forcing traffic through selected cut crossings. It does not yet meaningfully evaluate richer routing over quotient graphs with three or more sibling scopes.

Keep binary decomposition as a control in Phase 2, but do not generalize conclusions about quotient-graph routing from it.

### 3. Routing, state accounting, and failure locality currently use different information budgets

The compressed routing algorithm uses crossing-link information and exact local detail while traversing a scope.

`failure_locality`, however, defines each scope summary as all external crossing links plus exact shortest-path distances among stable boundary nodes.

`routing_state` and `churn` do not charge those boundary summaries.

As a result, the current `State`, `Stretch`, `Churn`, and `Failure Locality` numbers do not yet describe one consistent routing architecture. Phase 2 must associate every routing strategy with one declared summary model and charge exactly the state that strategy consumes.

### 4. Summary composability must become an explicit invariant

A parent scope must not derive its published summary by silently reading the full physical graph hidden inside descendants. Its externally visible summary must be derivable from:

- summaries published by immediate children;
- physical crossing information available at that scope boundary;
- state explicitly declared as locally detailed at that scope.

Otherwise hierarchy only hides information in the metric while the algorithm still depends on global knowledge.

Phase 2 should test summary construction bottom-up and make violations visible.

### 5. State ownership must be explicit

There are two different kinds of state:

- forwarding state installed at physical forwarders;
- control/topology/summary knowledge used to derive that forwarding state.

They should not be conflated, but neither should control knowledge be ignored. Phase 2 should report them separately and define who logically owns each summary object. Replication for availability is outside the current scope; one logical copy per declared consumer is enough for architecture accounting.

### 6. Failure locality is currently an oracle-style metric

The current implementation recomputes summaries directly from the failed physical graph. This is useful as an oracle, but it is not yet a propagation model.

Phase 2 locality should be strategy-specific and compositional: a child publishes a changed summary; the parent updates using only information it is allowed to know; propagation continues only if the parent's own published summary changes.

The existing oracle metric may be retained under a separate name for comparison.

## What should not change yet

Do not add Endpoint ID, Rendezvous, Channel, transport, packet timing, queues, congestion control, security, wireless, or protocol wire formats.

Do not optimize the simulator for very large node counts yet.

Do not replace the current decomposition immediately. First vary summary information while keeping decomposition fixed, then vary decomposition as a separate experiment axis.

## Next step

Implement `docs/phase2-routing-summary.md` with the following additional invariants:

1. every summary strategy has an explicit information budget;
2. routing may consume only that information plus explicitly local detailed topology;
3. every persistent consumed object is charged to state;
4. summaries are composable bottom-up;
5. failure propagation uses the same summary model as routing;
6. binary decomposition remains a control, not an architectural conclusion.
