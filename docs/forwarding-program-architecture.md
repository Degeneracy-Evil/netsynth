# Forwarding Program Architecture

> Status: architecture choice after theory/prior-art reconciliation.
>
> This document resolves the main open data-plane question in NetSynth v0.1:
>
> How should an already-resolved route be divided between packet-carried information and reusable forwarding state?

## 1. Problem

Scale 4 has already chosen:

- Structured Locator as topology-dependent destination;
- Routing Scopes as knowledge/control ownership;
- BTG/STP as opaque reusable Scope contracts;
- destination-specific route resolution on demand;
- some packet-carried route state.

What remained open was the concrete information placement.

The architecture must avoid two bad extremes:

~~~text
all route detail in packet
    -> large headers, detailed path exposure, weak local repair

all route detail in routers
    -> large persistent tables, destination-specific churn
~~~

The correct design space is a resource trade-off.

## 2. Theory and modern-system reconciliation

### 2.1 Compact routing

Compact-routing theory establishes that routing-table state, packet/header information and path stretch are interchangeable resources with unavoidable lower bounds on general graphs.

Therefore no clean-slate architecture can simultaneously demand:

- tiny router state;
- tiny packet routing state;
- exact shortest paths;
- arbitrary graphs.

NetSynth must make the trade explicit rather than hiding one resource.

### 2.2 Optimal path encoding

Optimal path-encoding work shows that, once reusable forwarding entries are allowed to represent path fragments, selecting the minimum packet encoding is itself computationally hard.

This supports a compiler/synthesis view:

~~~text
abstract route
    +
available reusable forwarding state
    +
packet/state/hardware budgets
    ->
compiled forwarding representation
~~~

There is no reason to freeze one universally optimal encoding.

### 2.3 SCION: packet-heavy extreme

SCION is important evidence that packet-carried forwarding state is practical.

Endpoints combine path segments and packets carry hop-level forwarding information. Transit border routers can therefore forward using packet-carried path state rather than a conventional global destination FIB.

Useful lessons:

- packet-carried forwarding state can work at real scale;
- path information can be assembled from reusable control-plane segments;
- multipath/path-aware operation becomes natural;
- forwarding state in packets can reduce transit state.

Important differences from NetSynth:

- SCION exposes/selects a relatively detailed inter-domain path at endpoints;
- its packet header contains hop fields;
- local path change can invalidate packet-carried path information;
- its hierarchy is tied to AS/ISD architecture and deployment policy.

NetSynth wants stronger Scope opacity and internal repair, so it should not put descendant physical-hop detail in the packet.

### 2.4 MPLS / label swapping: state-heavy extreme

MPLS demonstrates the opposite resource placement.

A short locally meaningful label indexes forwarding state. Each hop may swap the label and choose the next hop.

Advantages:

- very small per-packet forwarding identifier;
- simple fast-path lookup;
- detailed path state can remain hidden from the packet.

Cost:

- forwarding state must be installed in the network;
- too much per-flow/per-route state harms scalability;
- nested tunnels traditionally use a packet label stack.

NetSynth should reuse the local-token / label-swapping principle without inheriting MPLS FEC/signaling/compatibility semantics.

### 2.5 Binding SID: reusable macro

Segment Routing's Binding SID is particularly close to an STP.

One short identifier can stand for a locally installed policy/segment list. The detailed policy is stored only where it is imposed, and may change while upstream users keep referring to the same binding.

This validates the use of reusable local **macro tokens** for NetSynth STPs.

### 2.6 Compact segment encodings

CRH and compressed SRv6 show two useful compression principles:

- use short domain/local identifiers;
- encode shared context once rather than repeating it per instruction.

NetSynth is not constrained by IPv6's 128-bit address/SID structure, so it can adopt these principles in a cleaner representation.

### 2.7 PolKA / algebraic route IDs

PolKA and related residue-number source-routing designs show that an entire exact path can be mathematically encoded in a route identifier and decoded locally.

This is valuable evidence that a path need not be represented as a literal list.

However, it is not chosen as the NetSynth common model because:

- it requires the edge/compiler to know the exact forwarding path;
- the encoded route is tightly coupled to node/port identifiers;
- local internal repair is less naturally hidden behind an opaque STP;
- special arithmetic and target support become part of the common fast path;
- the method optimizes one extreme: near-stateless core.

It remains an interesting profile/baseline.

### 2.8 Bloom-filter forwarding

In-packet Bloom-filter forwarding moves substantial forwarding state into the packet and is attractive for multicast.

False positives and security/authorization complications make probabilistic forwarding a poor correctness primitive for NetSynth unicast.

It remains research prior art, not a common forwarding semantic.

### 2.9 Programmable-switch reality

Modern programmable data planes such as P4 support protocol-independent parsing, tables and actions, but still rely on bounded packet parsing/header stacks and target-specific resource limits.

This reinforces an architecture requirement:

> forwarding work and writable packet state must be bounded before transmission.

The common NetSynth fast path should remain simpler than a general packet virtual machine.

## 3. Architecture choice: hybrid compiled forwarding

NetSynth chooses a **hybrid compiled forwarding model**.

The architecture distinguishes:

~~~text
Abstract Route Program
        |
        | compile
        v
Compiled Forwarding Program
        |
        +-- Packet Route Code
        +-- bounded Forwarding Context
        +-- reusable Scope-local Forwarding Bindings
~~~

The compiler decides where to place information.

## 4. Packet Route Code

The packet carries a finite route-code region created before transmission.

It represents only the routing choices that cannot be recovered from reusable local Scope state.

Conceptually it contains an ordered sequence of coarse actions such as:

~~~text
invoke STP X
cross parent-visible link Y
invoke STP Z
final local delivery
~~~

It does **not** contain descendant physical-hop paths hidden inside STPs.

### Properties

Packet Route Code is:

- destination-specific;
- finite and size-known at ingress;
- normally immutable except for an execution cursor/consumption metadata;
- composed from opaque Scope-local routing tokens;
- not globally meaningful as one universal source-route namespace.

The exact byte format is deferred.

## 5. Scope-local Forwarding Binding

A Scope may assign a short local token to a reusable STP or reusable forwarding subprogram.

Conceptually:

~~~text
token
    ->
Scope-owned forwarding binding
    ->
next forwarding action / local continuation
~~~

The token is not:

- an Endpoint identity;
- a Locator;
- globally unique;
- a flow/session identifier.

It is a reusable data-plane handle.

This is the clean-slate analogue of the useful parts of:

- MPLS labels;
- Binding SIDs;
- Pathlet FIDs.

## 6. Local identifier namespaces

Forwarding tokens are Scope-local.

The same numeric value may have unrelated meanings in unrelated Scopes.

A compiled token reference is interpreted under an explicit or already-known Scope context.

This lets implementations use identifiers sized to the local forwarding namespace instead of globally oversized identifiers.

Exact widths are profile/hardware choices.

## 7. Bounded Forwarding Context

A packet also reserves a bounded writable forwarding-context area before transmission.

It contains only execution state required by the chosen compiled representation, such as:

- route-code cursor;
- current local token;
- bounded continuation/scratch information.

The packet does not dynamically allocate more routing-header space in transit.

Therefore:

> packet wire length is fixed when it enters the network.

This closes the packet-size/PMTU contradiction exposed by the earlier recursive-stack model.

## 8. No general packet virtual machine

The Forwarding Program is called a "program" because it is compiled routing information, not because routers execute arbitrary code.

The common hot-path operations should remain a very small set, conceptually:

~~~text
READ_NEXT_ROUTE_TOKEN
LOOKUP_LOCAL_TOKEN
FORWARD
SWAP / REPLACE_CURRENT_TOKEN
ADVANCE_CURSOR
COMPLETE_LOCAL_STP
FAIL_CLOSED
DECREMENT_HOP_BUDGET
~~~

An implementation may fuse these operations.

No loops, arbitrary memory access or general computation are required in the common forwarding instruction model.

## 9. Composite STP execution

A composite STP may internally invoke immediate-child STPs.

The architecture no longer requires literal packet-stack expansion.

The forwarding compiler may represent the continuation using a combination of:

- reserved packet Forwarding Context;
- Scope-local continuation/binding tokens;
- inlining where cheap.

This is an explicit state-vs-packet trade.

### Example

Abstractly:

~~~text
parent P:
    action A
    invoke child C
    action B
~~~

Possible compilation A:

~~~text
packet context stores return/continuation
C uses less installed continuation state
~~~

Possible compilation B:

~~~text
child invocation uses a continuation-specialized binding token
more local forwarding state
less packet writable context
~~~

Both implement the same STP contract.

The architecture does not force one representation globally.

## 10. Context spilling

If a nested realization would exceed the packet's supported writable-context capacity, the compiler must not create an unexecutable packet.

It may instead:

- allocate/reuse an additional local binding/macro token;
- choose a more state-heavy representation;
- choose another route;
- reject compilation.

This is analogous to a compiler spilling temporary state from a limited register-like resource into reusable stored state.

No forwarding node may silently grow the packet in transit.

## 11. STP hard resource contract

An STP advertises a representation-independent hard forwarding requirement sufficient for a parent/compiler to know whether the STP is executable under a target profile.

Conceptually:

~~~text
ForwardingResourceRequirement {
    max_writable_context
    required_token/action capability class
}
~~~

The exact representation is not frozen.

The important rules are:

- requirement is a hard contract, not a soft route metric;
- same-generation internal repair must remain within the advertised requirement;
- exceeding it requires a new hard generation/contract;
- parent composition uses only immediate-child advertised requirements;
- parent does not inspect descendant realizations.

## 12. Route compilation

Route resolution first produces an Abstract Route Program.

The forwarding compiler then chooses a concrete representation according to:

~~~text
packet-route-code budget
writable-context capacity
available local forwarding bindings
table/state budget
update/churn cost
target forwarding capabilities
~~~

Path quality is already determined/considered by route resolution and may also enter compilation if several equivalent abstract routes exist.

The compiler does not require a globally optimal solution.

Heuristics/approximation are expected because the general encoding problem is hard.

## 13. Reuse policy

Persistent forwarding bindings should represent reusable routing objects, especially STPs and common subprograms.

They should not normally be created per packet or per transport Channel.

This preserves the Scale-4 rule:

> transit forwarding does not require per-flow network state.

A deployment may cache popular compiled macros opportunistically, but correctness cannot depend on unbounded per-flow installation.

## 14. Repair semantics

Suppose an active STP token X currently uses realization R1.

If an internal failure allows repair to R2 while preserving:

- ingress/egress contract;
- token/generation semantics;
- advertised forwarding-resource requirement;

then the Scope may update local forwarding bindings and continue using X.

Packets outside the Scope do not change.

If the replacement cannot satisfy the hard resource/forwarding contract:

- retire that generation;
- fail stale references closed;
- route resolution recompiles using another STP/generation.

## 15. Relation to the three extremes

### Traditional destination/FIB routing

~~~text
packet information: low
persistent router state: high
local repair: strong
~~~

### SCION-like full path-carried forwarding

~~~text
packet information: high
persistent path state in transit: low
endpoint/path visibility: high
local hidden repair: weaker
~~~

### NetSynth hybrid

~~~text
packet:
    coarse destination-specific route choices

Scope forwarding state:
    reusable opaque local path programs

result:
    packet does not expose physical descendant paths
    router does not store global per-destination routes
~~~

This is the intended middle point.

## 16. Packet-size consequence

Before a Channel packet is emitted, the compiler/packetizer knows:

~~~text
Packet Route Code bytes
Forwarding Context bytes
network envelope bytes
Channel / AEAD overhead
Path usable packet size
~~~

Thus Message fragmentation is deterministic for the chosen path representation.

Transit nodes never need to enlarge the packet.

## 17. Hardware profiles

The common semantic model is intentionally representation-neutral enough for different forwarding targets.

### Fixed-function / simple ASIC profile

May choose:
- fixed-width short tokens;
- small fixed Forwarding Context;
- label-style table lookup and swap;
- aggressive use of reusable binding tokens.

### Programmable-switch profile

May support:
- more compact variable instruction packing;
- slightly richer context operations;
- profile-specific route-code compression.

### Software-router profile

May use a denser/variable representation when CPU parsing cost is acceptable.

All profiles execute the same abstract STP/Route semantics.

## 18. What is not in the common model

The common architecture does not require:

- IP/MPLS/SRv6 wire compatibility;
- globally fixed token width;
- general source-selected routing;
- arbitrary packet programs;
- exact physical-hop lists in packets;
- algebraic route IDs;
- Bloom-filter forwarding;
- per-flow installed paths;
- unbounded recursive stack growth.

## 19. Minimal semantic validation

Before freezing this data-plane choice, one tiny validation should compare three compilations of the **same** Abstract Route Program:

1. packet-heavy inline encoding;
2. state-heavy binding-token encoding;
3. hybrid encoding with bounded writable context.

For each, measure only semantic resource counts:

- packet route-code bits/words;
- writable context;
- persistent local forwarding entries;
- forwarding lookups/mutations;
- update impact under one local STP repair;
- packet wire-size bound;
- route result.

The validation should show:

1. all representations realize the same physical route semantics;
2. Scope opacity is preserved by the chosen hybrid representation;
3. local STP repair can change hidden bindings without changing outer packet route code;
4. packet length never grows after ingress;
5. a context-capacity overflow can be compiled into additional local binding state;
6. no per-flow transit state is necessary;
7. stale hard-generation tokens fail closed;
8. the compiler needs only parent-visible/immediate-child resource contracts;
9. exact descendant physical paths never leak into parent route code.

Do not benchmark forwarding throughput yet.

## 20. Architecture decision

The NetSynth common data plane is therefore:

~~~text
Destination Locator
Hop Budget

Compiled Forwarding Program:
    finite Packet Route Code
    bounded writable Forwarding Context

Scope-local reusable forwarding bindings

Payload
~~~

The packet carries enough information to avoid global destination-specific transit state.

The network stores enough reusable local information to avoid carrying detailed physical paths.

The compiler is the boundary that explicitly trades those two resources.

This is the selected NetSynth forwarding-program architecture.
