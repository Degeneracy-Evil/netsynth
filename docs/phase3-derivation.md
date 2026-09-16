# Phase 3 Forwarding Derivation

> This document records the architectural derivation behind Phase 3. It is intentionally stricter than an implementation sketch: the purpose is to make hidden global knowledge impossible to mistake for deployable forwarding behavior.

## 1. Locator is a coordinate, not a path

For the current static ScopeTree hypothesis, a forwarding node has a topology-derived locator

```text
<c1, c2, ..., ck, local-selector>
```

where each `ci` identifies one child scope inside its parent and only needs to be unique in that parent. The root is implicit. The local selector is unique only inside the finest leaf scope.

Components are semantic hierarchy coordinates; they are not path instructions and do not imply that packets traverse the scope tree.

Portal and crossing references exposed by routing summaries must also use explicit locator references. Raw globally meaningful simulator node IDs are not part of the candidate architecture outside legitimate local detail.

The exact bit encoding remains out of scope. Phase 3 should count locator components/references so hierarchy depth is not information-theoretically free.

## 2. Progressive resolution

Let `L(u)` be the current forwarder's locator and `L(d)` the destination locator carried by the packet.

If `u` and `d` are in the same leaf, the destination is resolved by the leaf-local selector using exact local topology.

Otherwise, find the longest common scope prefix. At the first differing component, the shared parent scope `S` contains both the current node and destination, while the destination component identifies an immediate target child `T` of `S`.

The current forwarding problem is therefore not:

```text
find an optimal route to the final destination
```

but:

```text
reach target child T of the smallest currently relevant shared scope S
```

Once the packet enters `T`, one additional locator component becomes resolved and forwarding proceeds at finer resolution.

This is progressive refinement of destination position.

## 3. This is not tree routing

Within `S`, a route toward target child `T` may traverse arbitrary sibling scopes and physical cross-links represented by the quotient/summary graph. With three or more children, a route may legitimately be:

```text
A -> C -> D -> B(target)
```

rather than a parent/child tree walk.

However, the initial common-core candidate does not leave `S` merely to re-enter `S` as a shortcut. Likewise, after the packet enters target child `T`, forwarding refines inside `T` rather than deliberately leaving and re-entering it.

This restriction is not imposed because hierarchy should control physical paths. It follows from the information boundary: a pure boundary-transit summary does not tell an outer scope which ingress is best for an arbitrary interior destination. Choosing such a shortcut would require additional destination/prefix attachment information or an oracle.

Thus the initial candidate uses **non-decreasing locator-prefix resolution** while retaining arbitrary graph routing among siblings at the currently active resolution.

## 4. Canonical forwarding table semantics

The data plane should not run a recursive path planner per packet.

For a node `u`, forwarding state can be indexed naturally by locator prefixes:

- exact/local entries for other selectors in `u`'s leaf;
- for every ancestor scope `S` of `u`, one aggregate entry for each immediate child of `S` that does not contain `u`.

Conceptually:

```text
FIB_u[target-prefix] -> eligible physical next hop(s)
```

For bounded fanout, this requires roughly local-leaf detail plus the sum of sibling counts along the node's locator depth, rather than one entry per global endpoint.

At packet time:

```text
next_hop(u, destination_locator)
```

is a longest/relevant-prefix lookup over already synthesized forwarding state. The packet need not carry a source address or a selected full path for this mechanism.

The control plane may synthesize the FIB from summaries; the data plane consumes the result. These roles must remain separate in the simulator.

## 5. Personalized forwarding view

The information available to node `u` can be represented as a personalized multiresolution graph `V_u`.

Construct it by expanding only the branch that contains `u` all the way from the root to `u`'s finest local scope:

```text
root
  owner child: expanded
  remote siblings: summarized
      |
      owner child: expanded
      remote siblings: summarized
          |
          ...
              |
              local leaf: full detail
```

`V_u` contains:

- the exact physical topology of `u`'s local leaf;
- crossings at scopes on `u`'s ancestor lineage;
- published summaries of sibling/remote branches;
- explicit locator references for abstract portals and crossings.

It does not contain detailed topology hidden inside remote branches.

This gives a strong implementation property: because the owner's own branch is expanded to local physical detail, the first edge of a route synthesized from `u` is resolvable to a real local physical neighbor. Abstract summary edges may be used to evaluate remote transit, but they must never be executed as if they were one physical hop.

## 6. Initial control-plane synthesis rule

For each aggregate FIB target `T` at ancestor scope `S`:

1. use only `V_u` restricted to information legitimately visible at `S`;
2. treat first entry into target child `T` as success at this resolution;
3. allow summarized sibling scopes to act as transit regions if their published summary supports boundary-to-boundary transit;
4. compute a deterministic abstract route to any legitimate ingress of `T`;
5. install only the first physical next hop in `FIB_u[T-prefix]`.

The target child's hidden interior is not queried while selecting its ingress.

After crossing into `T`, the next forwarder resolves the next locator component using its own knowledge and FIB.

S0 may be unable to use a remote sibling as a transit region because it advertises no internal boundary connectivity. That is a legitimate consequence of its information budget, not a reason to consult hidden topology.

## 7. Boundary indistinguishability result

A strong limitation follows from the information model.

Consider a scope `T` with two boundary portals `a` and `b`, and an internal destination `x`. Construct two internal topologies with:

- the same scope hierarchy;
- the same locator for `x`;
- the same boundary set `{a, b}`;
- the same exact boundary-to-boundary distance `d(a,b)`;
- identical external topology.

In topology `G_a`, attach `x` very close to `a`. In topology `G_b`, attach `x` very close to `b`. This attachment can be arranged without changing the advertised `a <-> b` boundary distance.

An external forwarder using only the destination locator and boundary-transit summary observes identical information in both worlds. Therefore it must make the same ingress decision in both. Whichever ingress it chooses can be made arbitrarily worse in one of the two worlds by increasing the scope's internal diameter relative to the target attachment cost.

Therefore:

> Even an exact full boundary-to-boundary summary cannot, by itself, guarantee shortest or topology-independent bounded-stretch ingress to every arbitrary interior destination.

Phase-2 S3 oracle shortest-path recovery was possible because the oracle supplied precisely the hidden destination-attachment information excluded here.

## 8. What extra information could defeat the limitation

If Phase 3 shows that pure progressive refinement has unacceptable stretch, there are several distinct mechanisms to study. They must not be conflated:

### Prefix-attachment summaries

A scope may advertise how its boundary portals relate to one or more levels of descendant locator prefixes. For example, boundary-to-immediate-child costs leak one additional level of destination attachment without becoming per-endpoint state.

A configurable lookahead depth would create an explicit tradeoff between state and ingress quality.

### Locator-carried attachment hints

The destination locator or an associated reachability record may carry extra routing hints describing useful ingress/portal attachment. This moves information into destination metadata / packet setup rather than global routing state.

### Destination-specific forwarding state

Install routes for finer destination prefixes or individual destinations. This improves path selection by spending routing state.

### On-demand path query / setup

Ask remote control state for a path or ingress decision before/while establishing communication. This spends control traffic, latency, and possibly per-path state rather than continuously replicated topology state.

These are future experiment axes, not part of the initial Phase-3 common-core candidate.

## 9. Stable-loop question remains open

Independent nodes synthesize their FIBs from different personalized views. Even if every local abstract route appears sensible, the resulting physical next-hop relation is not automatically guaranteed to be globally loop-free.

Do not silently repair this with the full graph.

Phase 3 should expose:

- repeated-node loops;
- no-route outcomes;
- Hop-Budget exhaustion;
- whether a node's local abstract estimate improves or worsens at each hop where such a metric is meaningful.

If stable loops are significant, a later design can test an explicit monotone rank/potential for each target aggregate. Such a rank would be additional control state and must be charged.

Hop Budget remains the hard damage bound, especially once dynamic inconsistent routing is introduced, but it is not itself a route-correctness proof.

## 10. Runtime knowledge boundary

`ScopeTree` and the physical graph may exist in experiment construction and oracle/verifier code. They must not be reachable from the distributed forwarding API.

A runtime forwarding object should contain only:

- owner locator;
- local neighbor/link handles and legitimate local detailed topology;
- charged ancestor-scope views / summaries;
- precompiled prefix-indexed FIB entries;
- explicit locator references appearing in those objects.

A useful implementation test is that the distributed `next_hop()` method can operate if the global `Graph` and `ScopeTree` objects are not passed to it at all.

The separate executor may resolve a returned local link handle against the physical graph solely to validate execution and measure cost.

## 11. State accounting additions

Phase 3 should continue charging persistent summary and forwarding state, and additionally expose structural locator costs:

- packet destination-locator component count;
- locator depth distribution;
- forwarding-prefix key component counts;
- portal/crossing locator-reference component counts.

Do not pretend these are bytes yet. The purpose is to avoid treating variable-depth hierarchical names as zero-cost labels.

## 12. Expected Phase-3 interpretation

The main comparison becomes:

```text
Flat shortest path
    vs
Phase-2 recursive oracle
    vs
Distributed progressive-refinement forwarding
```

The oracle is an information upper bound, not a deployment candidate.

If S3 distributed forwarding loses path quality, that is expected and meaningful: it measures missing destination attachment information, not necessarily a bug in boundary summaries.

If the distributed architecture still reaches a useful state/stretch/failure-locality region on structured graphs, the core hypothesis remains promising. If hostile or even common graphs show unacceptable stretch or stable loops, the next experiment should spend information explicitly (for example prefix-attachment lookahead) rather than reintroducing hidden global knowledge.