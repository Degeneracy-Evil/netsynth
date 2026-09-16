# NetSynth Architecture Notes

> Status: exploratory architecture, not a protocol specification.
>
> This document records the reasoning that has survived the current design discussion. It intentionally distinguishes derived requirements from candidate mechanisms.

## 1. Goal and boundary

NetSynth asks a clean-slate question:

> If two independently designed computers needed a modern network, and we were free to redesign everything above the physical layer without compatibility constraints, what architecture would emerge as the network scales from two machines to a world-scale system?

Current exclusions are deliberate:

- no compatibility with Ethernet, IP, TCP, DNS, BGP, or existing APIs;
- no security or adversarial model yet;
- no wireless/shared-medium design yet;
- no weak-network assumptions such as high random loss or extreme jitter;
- no hardware-specific optimization as an architectural requirement.

The initial reference environment is a stable wired network. The long-term design must later be checked against at least three workload profiles:

- general-purpose wired systems;
- datacenter/HPC systems, where bandwidth and latency justify expensive hardware;
- constrained/IoT systems, where state, cost, power, and bandwidth are scarce.

A feature that is useful only to one profile should not enter the common core unless that profile cannot be expressed without it.

## 2. Design method

NetSynth is not designed top-down as a fixed protocol stack. It is derived by increasing scale and adding a concept only when the previous model fails.

The workflow is:

1. solve the smallest network that can exist;
2. increase only one major source of complexity at a time;
3. identify exactly what breaks;
4. add the smallest mechanism that restores correctness or scalability;
5. later revisit the full system from world scale and delete transitional abstractions that are no longer necessary;
6. finally verify that the global architecture gracefully degenerates back to the two-node case.

An abstraction is justified when it changes a complexity boundary, hides a different lifetime or scope, or contains failures/changes. It is not justified merely because it makes a diagram cleaner.

## 3. Current design principles

The following principles have survived the reasoning so far.

### 3.1 Context should not be redundantly encoded

If a fact is already implied by local context, it should not be repeated in every data unit. A point-to-point link does not need source and destination addresses merely to name the only two endpoints.

### 3.2 Fast-changing state should have small scope

A local queue change should remain local. A link failure should first be absorbed locally. A world-scale control event should occur only when world-scale reachability actually changes.

### 3.3 Global names may be large; global replicated state may not be

A huge identifier space is cheap. Requiring every forwarder to know every endpoint is not.

### 3.4 The data-plane core should remain deliberately poor

Forwarders should understand only what is required to forward. Endpoint identity, application service names, content names, detailed topology, and transport semantics should not enter the hot forwarding path unless later reasoning proves they are necessary.

### 3.5 Reachability and stability dominate exact global optimality

The baseline routing system should seek scalable reachability, stability, and reasonable paths, not continuous globally optimal paths. Local decisions may exploit multiple eligible next hops without requiring globally synchronized congestion state.

### 3.6 The physical connectivity is always a graph

Any hierarchy introduced later is a compression/knowledge structure, not a claim that physical connectivity is a tree.

## 4. Scale-by-scale derivation

### Scale 0: two machines, one point-to-point link

```
A ================= B
```

No addressing or routing is necessary. The first unavoidable problems are finite buffering, framing/boundaries, and producer/consumer rate mismatch.

The useful primitive is a direct **Link** carrying bounded opaque blocks. A link may implement local flow control/backpressure. Exact wire encoding, CRC/FEC, or retransmission mechanisms are implementation questions and are not yet common-core requirements.

Derived lesson: addressing is not intrinsic to communication; it appears only when a forwarding choice exists.

### Scale 1: branching and forwarding

```
       B
       |
A -----X
       |
       C
```

The intermediate node must choose an output. This creates **Forwarding** and a minimal forwarding selector. Competing inputs for one output also create congestion even on a perfect wired network.

Derived lessons:

- congestion is fundamentally resource contention, not merely packet loss or a bad medium;
- hop acceptance is different from end-to-end delivery;
- multi-queue/virtual-lane mechanisms may improve performance but are not yet common-core abstractions.

### Scale 2: static multi-hop mesh

Multiple paths force a choice about where path information lives: in the data unit, in per-path network state, or in destination-oriented routing state.

The current baseline is **target-based hop-by-hop forwarding**. The sender expresses where the data should go, while the network decides how to get there. Multiple eligible next hops are normal, not an extension.

The forwarding structure for a target can be viewed as a progress DAG rather than a single route. The network core does not promise ordering, because path diversity would otherwise be constrained by an upper-layer semantic.

Finite buffers plus arbitrary mesh traffic also show that globally lossless backpressure is not free: backpressure, dropping/refusal, or resource reservation must eventually resolve sustained overload and cyclic resource dependence. The common network core therefore does not promise end-to-end losslessness.

### Scale 3: dynamic mesh

Allowing links and forwarding nodes to fail/recover introduces a routing control plane. For a small network, disseminating the complete topology is acceptable.

Local failures should first be absorbed locally. Only reachability/topology changes that cannot be hidden locally need wider propagation.

Temporary inconsistency between forwarding states can produce loops. Requiring a globally synchronized routing transaction would be too expensive, so the data unit gains a finite **Hop Budget** to bound damage from transient control-plane inconsistency.

Control traffic must retain a progress guarantee even when normal data traffic is saturated; otherwise the network can become unable to distribute the information needed to recover.

### Scale 4: large network and routing compression

With flat targets and global full-topology knowledge, per-node state is O(N), and local-change dissemination can drive system-wide control work toward O(N^2).

The key observation is routing equivalence: from a remote observer's perspective, many destinations may be indistinguishable for a portion of the routing decision. Internal topology can then be compressed.

This motivates a candidate **Routing Scope**: a subgraph whose internal complexity is much larger than the boundary information required to represent it externally.

A scope is not a country, provider, company, datacenter, or administrative region. It is a topology-compression object.

Scopes are optional. If a portion of the graph has no useful separator/cluster structure, it should remain relatively flat rather than being forced into a hierarchy.

### Scale 5: endpoint relocation

Once a destination changes its attachment point, a topology-derived forwarding name cannot also be its stable name. This derives the separation:

```
Endpoint ID != Locator
```

An **Endpoint ID** is a stable, topology-independent name for a communication endpoint. A **Locator** is a replaceable forwarding name for one current attachment location.

An endpoint may have a Locator Set rather than one locator.

Stable identity plus independent movement creates a rendezvous lower bound: if two endpoints both move and lose their old locators, some third-party state must retain current reachability information if they are expected to find each other by stable ID.

This motivates a **Rendezvous** system mapping Endpoint ID to Locator Set. It is a cold/recovery path, not the packet forwarding path. Existing communicating endpoints should update locator information directly where possible.

## 5. Current candidate architecture

The current architecture is intentionally small:

```
Application / higher-level naming
             |
        Endpoint ID
             |
       Rendezvous (cold path)
             |
        Locator Set
             |
          Channel
             |
-------------+------------------
       forwarding core
-------------+------------------
 Structured Locator (candidate)
        Hop Budget
          Payload
             |
   hop-by-hop forwarding
             |
            Link
             |
            PHY
```

Two side control systems exist conceptually:

```
Routing control: topology -> forwarding state
Rendezvous:      Endpoint ID -> Locator Set
```

Neither should automatically become another mandatory data-plane layer.

## 6. Routing Scope and Structured Locator: current hypothesis

This is the main hypothesis to test next, not a frozen design.

The physical network remains an arbitrary graph G0. Where useful, subgraphs are contracted into a coarser quotient graph G1, which may in turn be compressed into G2, and so on. The result is a multi-resolution graph representation.

A scope is valuable when internal complexity greatly exceeds boundary complexity. Scope depth need not be uniform across the network.

The candidate structured locator is conceptually:

```
<s1, s2, ..., sk, local>
```

where each component is meaningful only inside its parent scope. Far-away forwarding uses coarse components; progressively more detail is relevant near the destination.

Important constraints:

- locator hierarchy is not a routing tree;
- physical and quotient-level connectivity remains an arbitrary graph;
- cross-scope links are normal;
- arbitrary overlapping scopes are currently disfavored because they can destroy aggregation;
- multihoming is represented by multiple locators rather than overlapping membership;
- scope membership and locator structure must change much more slowly than individual routes;
- scope restructuring should support old/new locator overlap rather than instantaneous global renumbering.

The unresolved trade-off is among:

- routing state;
- control churn;
- path stretch;
- boundary complexity;
- failure locality.

There is no assumption that all arbitrary graphs admit strong compression without path-quality loss.

## 7. Common core vs profiles

The common architecture should be judged against multiple profiles without becoming a union of their features.

### General-purpose wired

This is the primary reference profile during early design. It has moderate cost, bandwidth, topology complexity, and implementation resources.

### Datacenter/HPC

This profile may use richer local scheduling, explicit credits, large forwarding tables, multiple high-bandwidth paths, or specialized channel semantics. Those mechanisms should remain profile-specific unless the common architecture cannot express them.

### Constrained/IoT

This profile may require tiny local state and simplified routing. A good common architecture should permit a small flat scope or simple default next hop without forcing every node to implement world-scale mechanisms.

The desired property is graceful specialization, not one protocol stuffed with flags for every environment.

## 8. Explicit non-decisions

The following are intentionally unresolved:

- concrete locator bit layout or length;
- scope formation algorithm;
- exact routing algorithm inside or between scopes;
- exact boundary summary exposed by a scope;
- rendezvous implementation (DHT, recursive directory, etc.);
- channel/transport semantics;
- ports, process demultiplexing, services, and content naming;
- congestion-control algorithm;
- reliability and ordering semantics above the forwarding core;
- security, authentication, authorization, privacy, and adversarial routing;
- wireless/shared-medium behavior;
- weak-link behavior;
- wire-format encoding.

Existing Internet mechanisms may later be rediscovered, rejected, or adapted, but they are not assumptions.

## 9. Next architectural question

The next task is quantitative rather than another abstraction exercise:

> For which graph families does recursive scope compression materially reduce routing state and failure propagation while keeping path stretch acceptable?

This is the first question to be tested with the NetSynth simulator.
