# Phase 3 Architecture Review

> Reviewed implementation: `9fe7d7938aefb7f3df8c569045bdbe31ac7afc8e`
>
> Result: the Phase-3 knowledge boundary is substantially correct and the distributed results are meaningful. The next architectural issue is not shortest-path quality but a missing correctness invariant: compressed summaries must preserve physical reachability before they are evaluated for path quality.

## What Phase 3 established

Phase 3 successfully separates:

- published scope summaries;
- per-node forwarding knowledge and prefix FIBs;
- the Phase-2 recursive route constructor;
- the physical-graph executor used only to validate and price selected hops.

The runtime forwarding object contains no `Graph` or `ScopeTree`, and data-plane forwarding is a Locator/FIB lookup. This is the intended thin forwarding boundary.

The experiments also confirm the Phase-2 information-bound result: exact boundary-to-boundary transit information does not tell a remote source which ingress is best for an arbitrary interior destination. S3 can make the recursive reference route shortest while distributed forwarding still has substantial stretch, especially under skewed edge costs.

## Main findings

### 1. The recursive route constructor is not a numeric upper bound

The old `recursive_oracle` has more hidden information than distributed forwarding but also uses a particular heuristic route construction. For weak summaries, the distributed FIB may accidentally choose a shorter path than that heuristic.

Therefore rename its interpretation conceptually to **recursive reference with remote queries**. It is an information-privileged comparison, not a per-strategy mathematical upper bound on route quality.

The true path-quality lower bound remains Flat shortest path.

### 2. S0/S1 no-route exposes a missing summary correctness contract

The tree results are the strongest warning. A static connected tree has a unique physical path between every source and destination, yet S0/S1 can report `no_route`.

Some of this is expected for S0: raw child-crossing information alone may not describe how to transit a remote compressed child on the way to a higher-level boundary.

S1 has a more specific closure problem. A scope may need to publish one of its external boundary nodes to its parent, while the summaries received from its immediate children may omit the internal connectivity needed to reach that node. Bottom-up construction is composable syntactically, but the published abstraction is not necessarily **interface-closed**.

This means `no_route` currently mixes two very different phenomena:

- real physical disconnection;
- false negative caused by an over-compressed summary.

The candidate architecture should not accept the second as ordinary operation.

### 3. Reachability and optimization must be separated

Before asking whether a summary gives good stretch, require it to preserve reachability.

For a scope `S`, let `B(S)` be every physical boundary/interface node through which a parent may need to enter, leave, or transit `S`. The externally published summary must preserve the connectivity relation induced by the internal graph on `B(S)`.

At minimum:

> If two boundary interfaces are physically connected through `S`, the summary must contain an abstract route connecting their references after convergence.

The summary does not need to expose the exact path or exact distance.

This is a correctness invariant, not a path-quality feature.

### 4. Reachability preservation does not require O(B^2) state

A full pairwise boundary-distance matrix is sufficient but not necessary.

For reachability alone, a summary may represent each internal boundary-connected component using a virtual component/hub object and attach each reachable boundary interface to that object. For a connected scope this can be O(B) rather than O(B^2).

The virtual object is control-plane abstraction only. It is never a physical next hop; the local forwarder still emits only an adjacent physical neighbor.

This creates an important new baseline: a low-information summary that guarantees no false-negative reachability while making minimal claims about cost.

### 5. Failure locality naturally interacts with the reachability contract

A local edge failure that changes metrics but not boundary connectivity need not change the minimal reachability summary.

A bridge/cut failure that partitions boundary interfaces must change that summary and may legitimately propagate upward.

Thus reachability-preserving summaries may improve both correctness and locality semantics: only failures that change externally observable connectivity are forced to escape a scope at the minimal information level.

### 6. Current label-sensitivity numbers are end-to-end sensitivity, not one isolated cause

The current relabel experiment permutes node IDs before decomposition. The balanced decomposition, portal/landmark selection, and tie-breaking all depend partly on deterministic node ordering, so a relabel can change several mechanisms at once.

Keep this result: large sensitivity is undesirable. But do not attribute it specifically to S1 or landmark selection yet.

Later experiments should distinguish:

- decomposition sensitivity: relabel, then recompute decomposition;
- policy sensitivity under fixed structural decomposition: relabel an isomorphic graph and mapped ScopeTree together, then rerun summary/FIB selection.

### 7. Small-graph state comparisons are not scaling conclusions

For 16-node examples, Locator/reference overhead can make compressed state exceed Flat even when the asymptotic structure may scale better. Conversely, a small-state win does not prove good scaling.

Do not optimize simulator performance yet, but after semantic corrections test several modest sizes and report empirical state-growth curves.

## Architecture status after Phase 3

The following pieces are now strong enough to retain:

- topology-derived Structured Locator;
- Locator-prefix FIB as the data-plane interface;
- immutable per-node forwarding knowledge;
- local detailed topology plus progressively summarized remote topology;
- hop-by-hop forwarding with explicit no-route/loop/budget outcomes;
- separation of identity-free topology position from later Endpoint identity;
- summary information must be explicitly charged.

The unresolved problem is now narrower:

1. define a minimum reachability-preserving summary contract;
2. measure the path quality of that correctness floor;
3. only then add explicit destination-attachment information and measure its benefit.

## Recommended next order

1. Phase 3.1: reachability-preserving/interface-closed summaries.
2. Re-run exhaustive tree/mesh/random/expander tests and require zero false `no_route` on connected static graphs.
3. Phase 4: destination attachment / Locator-prefix lookahead as an explicit information-budget axis.
4. Only after that revisit decomposition fanout/quality.
