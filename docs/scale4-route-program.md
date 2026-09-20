# Scale 4 Route Program

> Status: architecture choice.
>
> NetSynth deliberately chooses packet-carried forwarding state for large-scale inter-Scope routing, while keeping route selection as a network function rather than an application-selected physical source route.

## 1. Why another Scale-4 choice is necessary

Routing Scope and Scoped Transit Pathlets reduce persistent topology knowledge, but they do not by themselves answer:

> Who stores the destination-specific choice of which pathlets to traverse?

The information can live primarily in:
- persistent per-destination router tables;
- per-route/per-flow network state;
- packet/session-carried route state.

General compact-routing theory proves that the first option can be made sublinear with stretch trade-offs.

NetSynth nevertheless prefers the third option for large-scale inter-Scope routing because its architecture priorities are:

- very small/simple transit forwarding state;
- strong containment of topology change;
- explicit information placement;
- reusable Scope-owned path services;
- willingness to pay bounded setup/header cost.

This is a design choice, not a theorem-imposed necessity.

## 2. Prior-art reconciliation

### Pathlet Routing

Pathlet Routing advertises path fragments and lets senders concatenate them into source routes represented by forwarding identifiers.

NetSynth directly borrows the idea of reusable path fragments/FIDs.

It does not make application-controlled route choice a common-core requirement.

### MPLS / Segment Routing

Label switching provides the push/swap/pop execution machinery.

Segment Routing demonstrates the broader trade-off of moving route instructions to a headend and packet header instead of maintaining per-flow state throughout the network.

NetSynth uses a more recursively summarized Scope/pathlet representation rather than node/link segment lists as its architectural object.

### SCION

SCION's control plane discovers path segments, endpoints perform path lookup/combination, and packets carry forwarding state.

This is direct prior art for packet-carried route state in a clean-slate Internet architecture.

NetSynth does not claim packet-carried forwarding state or path-segment composition as novel.

The NetSynth-specific choice is the combination with topology-derived Routing Scopes whose advertised pathlets are intended primarily for state ownership and local change containment, without importing SCION's AS/ISD, trust, security, or endpoint-path-control semantics.

## 3. Architecture choice: Route Program

For large-scale inter-Scope routing, the network compiles a **Route Program** from:

~~~text
Source forwarding position
Destination Structured Locator
current Scope/pathlet control state
~~~

The Route Program is a sequence/composition of Scoped Transit Pathlet invocations and direct local/crossing actions.

It describes a route over the virtual topology, not a physical hop-by-hop source route.

Individual STPs may repair or recursively change their physical realization without changing the Route Program.

## 4. Who compiles the route

The application/source does not need global topology knowledge.

A local network-side **Route Compiler** associated with the source/ingress performs route resolution.

Logical interface:

~~~text
compile_route(source_position, DestinationLocator)
    -> RouteProgram
~~~

This is a control-plane function.

Its physical implementation may later be:
- local cached control state;
- recursive queries to Scope controllers;
- distributed control computation.

The architecture does not require a single global route server.

## 5. Route Compiler knowledge boundary

A compiler may use only routing information valid at its resolution level.

At a Scope boundary, it sees:
- immediate-child Boundary Transit Graphs;
- crossing links;
- higher/lower-level route objects obtained through explicit recursive queries.

It does not receive arbitrary descendant physical topology.

Thus route computation can be recursive while preserving Scope knowledge boundaries.

## 6. Packet format

The Scale-4 transit unit now becomes conceptually:

~~~text
TransitUnit {
    Destination Locator
    Hop Budget
    Route / Transit Stack
    Payload
}
~~~

The stack is populated by the Route Compiler at ingress and may be modified by pathlet realization.

The Destination Locator remains present because it:
- identifies the ultimate forwarding target independently of one compiled route;
- allows local/final destination delivery;
- provides context for route repair/recompilation;
- survives pathlet changes better than a pure source-route identity.

## 7. Data-plane behavior

### Inter-Scope / compiled mode

If a Route/Transit label is active:
- forwarding is label-switched;
- the top label selects the next STP/local action;
- composite STPs may push lower-level labels;
- labels are swapped/popped as pathlets progress.

### Local destination mode

When no compiled inter-Scope action remains, local routing may use the Destination Locator directly.

A small network or small leaf Scope can therefore operate without large-scale route-program machinery.

This preserves graceful degeneration.

## 8. No mandatory per-flow state in transit routers

A Route Program is carried by packets or cached at the communication edge.

Transit routers store reusable pathlet/FID forwarding state, not one entry per flow.

This is a deliberate state-placement choice.

A later Channel abstraction may cache Route Programs, but Scale 4 requires only that an ingress can reuse a recently compiled program.

## 9. Route Program is not raw physical source routing

The architecture intentionally distinguishes:

~~~text
physical source route:
    explicit sequence of physical routers/links

NetSynth Route Program:
    sequence/composition of reusable Scope-owned path services
~~~

A pathlet remains free to:
- choose among multiple physical realizations;
- repair around internal failure;
- change lower-level labels;
- use local multipath;

without changing the caller's high-level Route Program.

The packet therefore specifies coarse forwarding commitments, not exact physical motion.

## 10. Change containment

An internal topology change has three possible effects.

### Level 1: hidden repair

The affected STP still satisfies its advertised contract.

No parent summary or Route Program changes.

### Level 2: pathlet contract changes

The STP is withdrawn/replaced or its generation changes.

Only Route Programs referencing it become stale.

### Level 3: Scope-level contract changes

The parent-visible Boundary Transit Graph changes and route compilation above the Scope may need new information.

This gives a direct operational meaning to the principle:

> fast-changing detail should remain inside the smallest possible scope.

## 11. One-shot versus repeated communication

Scale 4 does not yet define a transport Channel, but Route Program reuse is permitted.

For a one-shot communication:
- compile;
- send with the resulting program.

For repeated communication:
- cache the program at the ingress/source networking layer;
- reuse it while referenced pathlet generations remain valid.

Scale 5 may later place this cache inside a longer-lived Channel abstraction when endpoint movement/identity is introduced.

## 12. Why NetSynth prefers this over universal compact hop-by-hop routing

A compact hop-by-hop scheme is mathematically valid and remains an important baseline.

NetSynth does not choose it as the primary Scale-4 common architecture because it places more destination-routing intelligence and persistent state into every transit forwarder.

The Route-Program design instead favors:
- simpler transit forwarding;
- path-specific information at the edge/packet;
- reusable local pathlets;
- local repair behind stable pathlet interfaces.

The costs are explicit:
- route-compile latency/work;
- packet header state;
- route-program invalidation.

These costs must later be measured.

## 13. Remaining problem: route discovery/compilation scalability

Packet-carried forwarding state does **not** make route computation free.

The next architecture problem is:

> How can the ingress Route Compiler obtain a good Route Program without itself needing a flat global pathlet graph or causing every local change to update every ingress?

This is now a control-plane discovery problem.

Theory/prior-art reconciliation should include:
- Pathlet Routing control dissemination;
- SCION path-segment discovery / path servers;
- compact routing and routing labels;
- hierarchical path computation;
- path-reporting oracles.

NetSynth must choose a control-plane route-discovery mechanism rather than hiding this state at the compiler.
