# Packet-Carried Routing Theory Reconciliation

> Status: architecture/theory reconciliation.
>
> This note pauses the previously proposed implementation of a fixed
> `max_additional_transit_slots` stack model. The later packet-size question
> exposed a broader, well-studied routing-information trade-off.
>
> NetSynth should model the fundamental resources first and choose an encoding
> only afterwards.

## 1. The actual problem

Scale 4 deliberately moved some destination/path-specific information from
persistent transit-router state into packet-carried Route Programs.

The question is therefore not merely:

> How deep can the recursive Transit Stack grow?

The real question is:

> How should forwarding information be divided among packet bits, reusable
> local forwarding state, writable packet context, path stretch and forwarding
> work?

This is a classical compact-routing / path-encoding trade-off.

## 2. Compact-routing theory

General compact-routing theory proves that routing-table space, packet/header
information and stretch cannot all be driven arbitrarily low on general graphs.

Name-independent compact routing provides concrete examples where
polylogarithmic writable packet headers reduce required local table state while
accepting bounded stretch. Lower bounds show that sublinear routing state
forces non-trivial stretch on some graph families.

Therefore packet-carried writable information is not an implementation hack.
It is one of the fundamental routing resources.

NetSynth should account for it explicitly.

## 3. Writable headers matter

Compact-routing work also shows that writable packet headers can change the
state lower bounds materially. An immutable destination-only header is much
more restrictive than a small amount of mutable transit information.

This supports the Scale-4 decision to permit mutable routing context.

It does **not** imply that the mutable context should specifically be a
literal recursively growing stack.

## 4. Path encoding is itself an optimization problem

Hari, Niesen and Wilfong formulate optimal path encoding when reusable switch
forwarding entries can stand for path fragments.

They show that the optimal path-encoding problem is APX-hard and give a
constant-factor approximation.

The architectural lesson is important:

> Route-program encoding should be treated as a synthesis/optimization problem
> over packet bits and installed reusable state, not as one fixed canonical
> stack representation.

NetSynth should not claim to have a uniquely optimal path encoding.

## 5. Pathlet Routing: useful abstraction, important warning

Pathlet Routing already implements compositional path fragments using local
Forwarding Identifiers (FIDs).

A forwarding entry may replace/pop one FID and push a sequence of FIDs that
realizes the advertised pathlet.

This strongly validates NetSynth's STP abstraction.

However, it also exposes exactly the issue found by the packet-size derivation:

> recursive macro expansion can increase the packet's FID sequence while the
> packet is in flight.

NetSynth should borrow the path-fragment abstraction without freezing this
specific push-FID wire behavior.

## 6. Binding Segment: closest modern analogue to STP

Segment Routing defines a Binding SID (BSID) that represents an SR Policy,
which may itself contain a segment list.

The important properties are:

- upstream carries a short local/global binding token;
- detailed policy state is stored only where it is imposed;
- the policy can change without changing upstream users of the BSID;
- the token provides opacity and state aggregation.

This is almost exactly the architectural role of a NetSynth STP.

The NetSynth-specific difference remains:
- STPs are owned by topology/control Scopes;
- parent knowledge is restricted to immediate-child contracts;
- route resolution is pull-based;
- no IP/MPLS compatibility is required.

## 7. Modern segment-list compression

Modern SR work exposes two separate compression ideas.

### Compact Routing Header (CRH)

RFC 9631 defines compact 16-bit / 32-bit path identifiers within a limited
domain.

Lesson for NetSynth:

> forwarding instructions should use scope-local compact identifiers sized for
> the local namespace, not globally overprovisioned identifiers.

NetSynth is not constrained to CRH's IPv6 encapsulation or 16/32-bit choices.

### Compressed SRv6 SIDs

RFC 9800 compresses repeated structure by sharing Locator-Block context and
packing shorter CSIDs.

Lesson for NetSynth:

> common routing context should be represented once rather than repeated in
> every instruction.

Much of the concrete SRv6 mechanism exists because a compatible design must
continue to inhabit 128-bit IPv6 SID/address structure. NetSynth should take
the compression principle, not the compatibility machinery.

## 8. Maximum SID Depth: capability, not architecture encoding

SR deployments explicitly advertise Maximum SID Depth so path computation
does not produce a legal logical path that hardware cannot impose.

This validates a NetSynth requirement:

> Route compilation must know the forwarding-context capability bound before
> transmitting the packet.

But the bound should not prematurely be defined as "number of nested stack
slots".

The implementation may use:
- a stack;
- a compact instruction tape;
- binding/macro tokens;
- local label swapping;
- a hybrid.

The common contract should be expressed in representation-independent resource
units, eventually bytes/bits or an explicitly negotiated forwarding-context
capacity.

## 9. SlickPackets: packet-carried robustness

SlickPackets carries a compact forwarding DAG in each packet so intermediate
routers can choose failure alternatives without storing all alternate paths.

It demonstrates that packet-carried forwarding state can encode more than one
linear route.

It is useful evidence that:
- packet state can buy local failure freedom;
- a packet program need not be a simple list.

NetSynth does not adopt SlickPackets directly because its source needs a
larger network map and the packet exposes the detailed forwarding subgraph.
That conflicts with NetSynth Scope opacity and local-repair goals.

## 10. Clean-slate implication

Because NetSynth has no IPv4/IPv6/MPLS/SRv6 compatibility requirement, it
should not inherit:

- 128-bit per-segment identifiers;
- IPv6 Routing Header structure;
- MPLS fixed label-stack semantics;
- SRH compatibility processing;
- globally uniform instruction width.

Instead the architecture should exploit:

- Scope-local namespaces;
- short local tokens;
- shared implicit Scope context;
- variable/compact encoding where hardware permits;
- reusable binding/pathlet tokens for common subprograms.

## 11. Revised resource model

The routing architecture should account for at least five resources.

### Persistent forwarding state

Reusable STP / local forwarding entries installed in Scope-owned forwarding
state.

### Packet route-code bits

The immutable/preallocated packet-carried representation of the selected
Route Program.

### Writable forwarding context

Bounded scratch/continuation state that forwarding may mutate while executing
the Route Program.

### Forwarding processing

Number/type of local lookups, decoding operations and context mutations.

### Path quality

Stretch / route metric induced by the chosen routing construction.

No architecture claim should optimize one while hiding the others.

## 12. Revised STP hard contract

The earlier proposed field:

~~~text
max_additional_transit_slots
~~~

is too representation-specific.

Replace it conceptually with:

~~~text
ForwardingContextRequirement
~~~

meaning:

> a conservative upper bound on the packet-resident writable working context
> required to execute this STP under the selected forwarding encoding.

The eventual data plane may express this in:
- bytes;
- bits;
- fixed context words;
- another explicit resource unit.

A same-generation repair is valid only if it remains within the advertised
hard requirement.

The parent computes composition using only immediate-child advertised
requirements, never descendant realizations.

## 13. Route Program becomes a compiled representation

Conceptually distinguish:

~~~text
Abstract Route Program
    sequence/composition of STP actions

Compiled Forwarding Program
    concrete packet/state encoding chosen for a forwarding profile
~~~

The compiler may choose among equivalent encodings:

- inline local FID;
- Binding/STP token;
- compressed sequence of local tokens;
- local-state-heavy encoding with smaller packet code;
- packet-heavy encoding with less persistent state.

This is a synthesis problem subject to explicit budgets.

## 14. Packet-size interaction

At packetization time the forwarding representation is already compiled.

The packetizer therefore knows:

~~~text
route_code_bytes
reserved_writable_context_bytes
network + Channel + AEAD overhead
usable_path_packet_size
~~~

and computes the remaining payload capacity.

The packet wire length must not grow beyond the ingress-reserved capacity.

A forwarding implementation may rewrite, consume or reuse the reserved routing
area, but may not require unbounded dynamic enlargement.

## 15. Implication for PMTU

DPLPMTUD remains the right endpoint principle.

RFC 8899 explicitly places PMTU discovery at the Packetization Layer and does
not require reliance on router-generated Packet-Too-Big feedback.

NetSynth Channel Path State already provides:
- endpoint acknowledgement;
- per-path state;
- repacketization under new Packet Numbers.

Thus PMTU discovery should remain endpoint/path-specific.

But it must operate on the **compiled forwarding representation**, not on a
fictional fixed-size Transit Stack.

## 16. What should be changed now

Do not implement the previous packet-size prompt yet.

First revise the architecture vocabulary:

1. keep STP / Boundary Transit Graph;
2. keep packet-carried Route Programs;
3. keep bounded mutable forwarding context;
4. stop treating recursive stack expansion as the architectural representation;
5. generalize the hard Context Budget from stack slots to representation-independent forwarding-context requirement;
6. distinguish Abstract Route Program from Compiled Forwarding Program;
7. explicitly account packet code, writable context, installed forwarding state and processing cost.

Only then should a minimal semantic prototype compare two or three encodings.

## 17. Minimal theory-driven validation later

The relevant NetSynth experiment is not a PMTU benchmark.

Use one tiny route/pathlet composition and show equivalent execution under,
for example:

- inline FID sequence;
- Binding/STP macro token with more installed forwarding state;
- bounded writable-context recursive encoding.

Charge:
- packet bits;
- installed forwarding entries;
- forwarding lookups/mutations;
- path result;
- maximum wire size.

The purpose is to prove the resource model is real and implementation-neutral,
not to find a globally optimal encoding.

## 18. Architecture status

The previous `Transit Context Budget` insight remains correct at a higher
level:

> packet-carried forwarding requires a hard, compiler-visible resource bound.

What changes is the abstraction:

~~~text
NOT:
    architecture = nested label stack
    budget = stack depth

INSTEAD:
    architecture = bounded packet-carried forwarding program
    budget = explicit packet-code + writable-context resources
    encoding = synthesis / implementation choice
~~~

This better matches both routing theory and modern forwarding practice.
