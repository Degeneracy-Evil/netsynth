# Phase 3 Implementation Contract

Read this together with `phase3-forwarding-semantics.md` and `phase3-derivation.md`.

The first distributed candidate must implement the following semantics rather than inventing another routing model.

## Runtime packet

The forwarding decision receives only:

```text
destination_locator
hop_budget
```

plus the current node's immutable forwarding knowledge. Payload is irrelevant to routing. No source address, global target node ID, full path, or hidden route oracle is available.

## Locator

Represent a forwarding-node locator as a typed sequence of local child-scope components followed by a leaf-local selector. Portal/crossing references exposed outside local detail must use locators, not globally meaningful simulator node IDs.

## Active resolution

For current node `u` and destination locator `D`:

1. if `D` resolves to a selector in `u`'s local leaf, use exact local forwarding;
2. otherwise find the longest common scope prefix of `L(u)` and `D`;
3. the next destination object is the immediate child prefix of that shared scope selected by the next component of `D`;
4. forwarding at this resolution terminates conceptually when the packet first enters that target child; the next node then refines the locator further.

Do not query the target child's hidden interior to choose its ingress.

## Prefix-resolution invariant

The initial candidate must not deliberately leave the currently active shared scope and later re-enter it as a shortcut.

A chosen physical next hop must not reduce the number of destination locator scope components already shared with the current node.

Equal prefix resolution is allowed while traversing sibling/transit structure. Increasing prefix resolution means the packet has entered a more specific destination aggregate.

This is an information-boundary rule for the initial candidate, not a claim that physical topology is a tree.

## Personalized view

Build per-node knowledge as a personalized multiresolution view:

- expand the owner's own hierarchy branch down to exact local-leaf topology;
- keep remote sibling branches summarized according to S0/S1/S2/S3;
- include only charged crossings, summary objects, and explicit locator references.

The distributed forwarding API must not receive `Graph` or `ScopeTree`.

The first edge selected from an owner's view must resolve to an actual local physical neighbor. Abstract summary edges may influence route synthesis but cannot be executed as one hop.

## Control plane and data plane

Compile persistent prefix-indexed forwarding entries before packet execution.

Conceptually:

```text
FIB_u[target_prefix] -> physical next hop (or eligible next-hop set)
```

The data-plane `next_hop()` performs a lookup over this charged state. It must not run the Phase-2 recursive oracle.

For the initial implementation, deterministic single-next-hop selection is sufficient. Multipath policy is not a Phase-3 requirement.

## Target aggregate synthesis

When compiling an entry for target child `T` of scope `S`:

- use only the owner's personalized view;
- treat first legitimate entry into `T` as success;
- allow other siblings of `S` to be transit regions only to the extent their published summaries expose usable boundary transit;
- do not use exact boundary-to-final-destination cost inside `T`;
- install only the resulting first physical hop.

## Oracle separation

Keep the existing recursive router as `recursive_oracle` (or equivalent) for comparison only.

Every experiment must distinguish:

```text
flat shortest path
recursive oracle
distributed forwarding
```

No distributed failure may fall back to the oracle or global shortest path.

## Execution and failures

A separate executor may use the physical graph only after `next_hop()` returns, to validate adjacency, apply link/node failures, accumulate real cost, and detect delivery/failure.

Report separately:

- delivered routes;
- no-route decisions;
- invalid/non-adjacent decisions (should be correctness failures);
- repeated-node loops;
- Hop-Budget exhaustion.

Do not silently repair any of them.

## State accounting

Continue Phase-2 persistent-state accounting and additionally report:

- destination locator depth/components;
- per-node own-locator components;
- forwarding-prefix key component counts;
- portal/crossing locator-reference component counts.

These are structural scalar/component counts, not byte or wire-format claims.

## Required negative test

Add an indistinguishability test with two remote target-scope interiors that have the same published boundary summary and the same destination locator but different hidden target attachment. A remote source's compiled ingress/next-hop decision must remain identical until some legitimately visible information changes.

This test guards against reintroducing the Phase-2 destination-attachment oracle.

## Not yet included

Do not add:

- prefix-attachment lookahead summaries;
- destination-carried attachment hints;
- destination-specific global routes;
- on-demand path queries;
- monotone rank/potential advertisements;
- scope controllers;
- decomposition optimization.

If Phase 3 shows unacceptable stretch or stable loops, those become explicit next experiment axes rather than hidden fixes.