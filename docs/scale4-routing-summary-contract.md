# Scale 4 Routing Summary Contract

> Status: architecture choice after theory reconciliation.
>
> This document answers one question only:
>
> What does a child Routing Scope export to its parent?

## 1. Architecture requirements

A child Scope summary must satisfy four different requirements.

1. **Sparse** — its size should depend primarily on boundary complexity, not interior node count.
2. **Path-realizable** — every routing object exposed to the parent must correspond to a real physical route that the child can execute.
3. **Opaque** — the parent must not learn arbitrary descendant topology or query hidden descendant shortest paths.
4. **Change-containing** — the child should be allowed to repair an internal route without changing the parent-visible object when the external promise remains valid.

A pure distance matrix satisfies neither sparsity nor change locality well.

A connectivity component summary is sparse but too weak for path-quality decisions.

A distance oracle is insufficient because a distance estimate is not itself an executable forwarding action.

## 2. Theory reconciliation

Let B(S) be the boundary interfaces of Scope S.

Compressing all pairwise distances among B(S) is a terminal-metric sparsification problem.

Relevant theory includes:
- metric/subsetwise spanners;
- terminal distance sparsifiers and distance-approximating minors;
- distance preservers;
- path-reporting distance oracles.

Exact terminal-distance compression is expensive in the worst case. General graphs can require quadratic-scale structure for low/exact distortion.

Applying a sparse-spanner construction to the complete metric closure on B(S) gives a sparse set of virtual terminal-to-terminal edges, each of which can be realized by a real internal path. For example, standard weighted-spanner theory gives a (2k-1)-spanner on |B| terminals with about O(|B|^(1+1/k)) edges.

However, NetSynth must **not** independently apply a constant-stretch spanner at every hierarchy level and claim the same global stretch. Recursive approximation factors can compound. End-to-end quality must be justified by the global routing construction.

Therefore the architecture contract should define executable path fragments, while the algorithm selecting those fragments must be theory-backed separately.

## 3. Prior architecture: Pathlet Routing

Pathlet Routing (Godfrey, Ganichev, Shenker, Stoica, SIGCOMM 2009) already introduced:
- virtual routing nodes;
- advertised path fragments called pathlets;
- locally scoped forwarding identifiers;
- recursive/composite pathlets;
- packet-carried forwarding-identifier sequences.

NetSynth adopts the mature idea that a summarized route fragment should have a local forwarding identity and a physical realization.

NetSynth does **not** adopt Pathlet Routing's global source-controlled route semantics as the Scale-4 architecture.

The NetSynth destination remains target-oriented through the Structured Locator. Path fragments are internal network routing objects, not an end-to-end path selected by the source.

## 4. Architecture choice: Scoped Transit Pathlet

A child Scope exports a **Boundary Transit Graph** whose vertices are only real physical boundary interfaces.

~~~text
BTG(S) = ( B(S), P(S) )
~~~

Each edge in P(S) is a **Scoped Transit Pathlet (STP)**.

A pathlet contains conceptually:

~~~text
ScopedTransitPathlet {
    local_forwarding_id
    ingress_boundary
    egress_boundary
    generation
    soft_metric
}
~~~

Exact encoding is undecided.

### Physical-vertex rule

Every BTG vertex is a real boundary interface.

NetSynth deliberately does not expose invented virtual routing vertices in the parent-visible contract.

This is an operational-simplicity choice, not a claim that Steiner vertices or distance-sparsifier vertices are mathematically useless.

## 5. Hard pathlet guarantee

While an STP is advertised as valid, its owner Scope guarantees:

1. a packet accepted at the ingress can be delivered to the egress;
2. the realization remains entirely within the owner Scope;
3. realization uses only physical links and recursively valid lower-level routing objects;
4. the parent does not need to know the realization path.

Path quality is deliberately **not** part of the hard forwarding contract.

An STP may separately advertise a soft metric such as current estimated cost. That metric is used for route selection, but changing it does not by itself invalidate the pathlet generation.

## 6. Internal repair without external churn

A child may change the physical realization of an STP without updating its parent when all externally visible properties remain valid:

~~~text
same ingress
same egress
same local forwarding ID
same generation
the ingress-to-egress transit service remains realizable
~~~

Thus an internal link failure may be repaired completely inside the child if an alternate realization satisfies the existing promise.

The hard summary changes only when a parent-visible forwarding promise can no longer be met. Soft metric updates may be published independently and may be coalesced or delayed without changing pathlet identity.

This is the main operational advantage of exporting path services rather than exact current shortest-path distances.

## 7. Reachability floor

For each internally connected component of B(S), the exported BTG must connect all boundary interfaces in that component.

Therefore:

~~~text
internal boundary reachability
    iff
BTG reachability
~~~

for the converged contract.

This subsumes the useful correctness property previously isolated by R0.

It does **not** require exact boundary distances.

A minimal contract can therefore be a tree/forest of transit pathlets. Additional pathlets improve route quality and/or resilience.

## 8. Quality state is explicitly optional above the reachability floor

The mandatory architecture semantics are:
- reachability preservation;
- physical realizability;
- stable hard forwarding semantics;
- recursive ownership.

The architecture does **not** mandate an independent alpha-spanner construction inside every Scope.

Additional STPs should be selected by a routing construction with a proven **end-to-end** state/stretch guarantee.

A single-Scope terminal metric spanner is a valid implementation/reference tool, but naively nesting one at every hierarchy level is not the NetSynth routing theorem.

This prevents the hierarchy from silently multiplying local approximation factors.

## 9. Parent view

For a parent Scope P with children C1...Cm, its routing-control view contains only:

~~~text
BTG(C1)
BTG(C2)
...
BTG(Cm)
physical crossing links between immediate children
~~~

No descendant physical topology is visible.

This graph is sufficient to describe every route that the children have explicitly promised to realize.

## 10. Bottom-up composition

A parent may construct one of its own STPs as a path through its child-level view.

A realization witness can contain:
- a physical crossing link;
- an STP exported by an immediate child;
- another crossing link;
- another child STP;
- etc.

The parent exports only the resulting opaque STP to its own parent.

Thus summary construction remains recursively composable without revealing descendant topology.

## 11. Destination semantics remain separate

An STP has:
- an ingress boundary;
- an egress boundary;
- a local forwarding identity.

It is **not** a destination identity.

The final packet destination remains the Structured Locator.

This distinction allows a route toward destination D to temporarily transit through the Scope containing D, leave it again, and later enter it for final delivery. Scope hierarchy therefore does not constrain path geometry.

## 12. Why the current packet format is now under pressure

The Scale-4 packet candidate is still:

~~~text
Destination Locator
Hop Budget
Payload
~~~

But an STP is an opaque locally owned routing service.

If the parent selects a child STP, the child needs to know which STP is being invoked. The final Destination Locator alone generally cannot encode that fact without duplicating destination-specific forwarding state throughout the child.

Therefore the STP contract creates a concrete architecture pressure for **temporary packet routing context**.

This is no longer a generic-theory argument for writable headers. It is forced by the chosen NetSynth summary semantics.

## 13. Recursive realization and Pathlet prior art

A parent STP may itself be realized using child STPs.

Pathlet Routing solved the analogous continuation problem using forwarding-identifier sequences carried in the packet.

NetSynth should reuse that insight rather than reinvent it.

However, the next architecture question is narrower:

> Can NetSynth use a small, dynamically pushed scope-local transit context so that routing remains destination-driven, rather than placing an end-to-end source route in the packet?

Do not settle that question in this document.

## 14. What is deliberately not in this contract

The BTG/STP contract does not yet specify:
- the algorithm selecting optional quality pathlets;
- a universal global stretch constant;
- how many redundant pathlets are required for failures;
- congestion/capacity promises;
- bandwidth reservation;
- source routing;
- the exact FID encoding;
- the temporary packet-context format;
- asynchronous contract publication protocol.

Those require their own architecture questions and theory reconciliation.

## 15. Minimal future validation

Once packet realization semantics are defined, validation should check only NetSynth-specific properties:

- parent cannot see descendant topology;
- every STP invocation is physically realizable;
- recursive STP realization terminates correctly;
- internal reroute can occur without parent-visible churn when the service ceiling remains valid;
- BTG reachability exactly matches boundary reachability;
- measured state includes realization/FID state.

Do not run experiments to rediscover generic spanner state/stretch bounds.

## 16. Next architecture question

The next forced problem is now:

> How does a packet invoke and recursively realize an STP without requiring per-flow state in routers or turning the whole network into source routing?

Theory/prior-art reconciliation must include at least:
- Pathlet Routing;
- MPLS-style label stacks;
- Segment Routing;
- recursive source-routing / path labels;
- compact-routing writable headers.

Only then should NetSynth choose the exact temporary transit-context semantics.
