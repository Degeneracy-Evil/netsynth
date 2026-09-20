# Theory-Driven Architecture Revision

> Status: design reconciliation in progress. This document does not authorize implementation.
>
> NetSynth remains clean-slate at the protocol/compatibility layer, but adopts established routing, graph, metric, and distributed-algorithm theory whenever the model applies.

## 1. The central correction

The current code and architecture prematurely promoted one experimental family into the universal model:

```text
laminar ScopeTree
    -> Structured Locator
    -> prefix-indexed FIB
    -> scoped potential
```

Theory reconciliation shows that this is only one possible **routing-label scheme**.

General compact-routing constructions may instead use landmarks, bunches/clusters, tree covers, sparse overlapping covers, writable packet headers, and handshakes. Sparse-cover hierarchies need not be laminar; a node may belong to multiple clusters at one scale, with bounded overlap.

Therefore the common NetSynth routing core should describe the *interface and resource placement* of a routing scheme, not prescribe a ScopeTree representation.

## 2. Revised naming model

Keep the stable application-facing concept:

```text
Endpoint ID
```

but generalize the cold-path result from "Locator Set" to:

```text
Routing Descriptor Set
```

A Routing Descriptor is scheme-defined topology-dependent information sufficient to initiate hot-path routing.

Examples:

- the current Structured Locator;
- a compact-routing node label;
- a tuple of landmark/tree-cover labels;
- another scheme-specific destination descriptor.

This prevents the architecture from assuming that routing-relevant information must be a hierarchical geographic-like coordinate.

### Candidate lifetime split

```text
Endpoint ID
    |
    | Rendezvous / resolution
    v
Routing Descriptor Set
    |
    | optional handshake / Channel setup
    v
Session Routing Context
    |
    v
Packet Routing Header
```

The exact relationship is scheme-specific.

## 3. Channel becomes theoretically meaningful

Compact-routing literature explicitly studies handshake/session routing: a first exchange may use a worse route to establish information that lets subsequent packets use a better compact route.

This matches NetSynth's independently derived long-lived Channel abstraction.

Therefore Channel should later be compared in at least two modes:

- **one-shot/direct:** resolve a Routing Descriptor and send immediately;
- **session:** resolve, perform a compact-routing handshake if useful, cache Session Routing Context, then amortize setup over subsequent traffic.

The simulator must measure setup stretch/cost separately from steady-state route stretch.

## 4. Packet header is a first-class resource axis

The previous candidate packet:

```text
Destination Structured Locator
Hop Budget
Payload
```

is too restrictive as a common-core assumption.

Compact-routing theory shows that writable headers can trade packet bits for substantially less router state. Therefore NetSynth should not force routing information entirely into the destination label and local tables.

The common model should permit a bounded scheme-specific mutable routing header.

Conceptually:

```text
Packet {
    destination / routing input
    mutable routing header
    Hop Budget
    payload
}
```

The routing header may be empty for simple schemes.

Resource accounting must keep distinct:

- destination/routing-label bits;
- initial header bits;
- maximum mutable-header bits;
- per-node routing-table bits;
- persistent control-plane bits;
- optional per-Channel/session state bits;
- setup/handshake traffic.

## 5. ScopeTree is no longer a universal primitive

Routing Scope remains a useful hypothesis and may still be valuable operationally, but it is not the universal representation.

Reasons:

1. sparse neighborhood covers use overlapping clusters with bounded overlap;
2. landmark/bunch schemes are not naturally represented by one laminar tree;
3. tree covers can provide multiple candidate routing trees;
4. low-doubling and specialized graph families admit different representations.

The simulator should support generic cluster/cover membership.

Possible scheme-specific structures include:

- laminar ScopeTree;
- multiscale overlapping Cover;
- landmark hierarchy;
- tree cover;
- physical spanner;
- emulator/hopset;
- no hierarchy at all.

Do not force these through ScopeTree adapters merely for code reuse.

## 6. Distinguish mathematical object types

The current implementation often converts many objects into abstract `usable_edges()`. This hides important semantic differences.

Future architecture should distinguish:

### Routing scheme

Directly defines hop-by-hop forwarding from local table + packet header.

### Distance oracle

Answers approximate/exact distance queries. It does **not** automatically provide a legal route.

### Path-reporting oracle

Provides route/path information in addition to distance.

### Spanner

A sparse **physical-edge subgraph**. Its edges are already realizable physical links.

### Emulator

A sparse weighted graph that may contain virtual edges. Every virtual edge requires explicit realization semantics if used by a packet network.

### Hopset

Virtual edges whose purpose includes bounding the number of hops in an approximate path.

### Cover / decomposition

A structural locality representation used by other algorithms; not itself forwarding.

This semantic separation is essential for future metric-repair work.

## 7. Revised common routing interface

A generic routing scheme should conceptually expose:

```text
preprocess(graph, naming inputs)
    -> RoutingDeployment

RoutingDeployment:
    routing_label(node)
    local_table(node)
    initialize_header(source, destination_descriptor, session_context?)
    next_hop(node, input_port?, header, local_table)
        -> physical_neighbor | delivered | failure,
           updated_header
```

Optional:

```text
setup(source, destination_descriptor)
    -> SessionRoutingContext
```

A scheme may be:

- name-dependent/labeled;
- name-independent;
- direct/fixed-header;
- writable-header;
- handshake/session-based;
- randomized.

The simulator core should not care which representation generated the table.

## 8. Theory-aware resource model

Replace "normalized scalar size" as the primary cross-scheme resource metric.

Keep structural record counts for debugging, but introduce explicit resource dimensions.

At minimum:

```text
routing_table_bits_per_node
routing_label_bits
initial_header_bits
max_header_bits
session_state_bits
persistent_control_bits_per_node
construction_messages
construction_rounds
update_messages
update_rounds
changed_persistent_bits
```

Because many theoretical bounds use machine words, add a declared bit-cost model:

- node identifier / routing-label reference;
- port identifier;
- edge weight;
- distance value;
- graph size/diameter parameters.

Never silently compare one scheme's record count against another scheme's bit bound.

## 9. Theory metadata must accompany each scheme

Every implemented theoretical baseline should carry machine-readable metadata:

```text
problem model
name-dependent / name-independent
graph assumptions
weight assumptions
stretch guarantee
table-space guarantee
label/header guarantee
construction model
dynamic/fault assumptions
citation
implementation fidelity
known deviations
```

Experimental output should distinguish:

- theorem guarantee;
- measured instance value;
- NetSynth-specific overhead.

## 10. Common core vs graph-family profiles

Established theory strongly supports profile-specific routing.

Examples:

- trees admit extremely compact exact routing labels;
- low-doubling metrics admit near-1-stretch labeled compact routing with polylogarithmic state;
- planar/minor-restricted families have strong separator/cover structure;
- arbitrary high-girth/expander-like graphs trigger universal lower bounds.

Therefore the NetSynth common core should be a generic routing execution/resource interface.

A profile may select a specialized routing construction when topology structure justifies it.

A universal general-graph compact-routing scheme should remain as a fallback/reference, not necessarily the mechanism every profile must use.

## 11. Revised interpretation of existing Phase code

The Phase 1-5 code should be preserved as a historical **Scope-routing experimental family**, not treated as the new universal simulator API.

Useful surviving pieces:

- physical graph representation;
- topology generation/import;
- failure-event representation;
- path validation;
- deterministic experiment infrastructure;
- some state/churn measurement ideas;
- Structured Locator / scoped-potential implementation as one routing scheme.

Scheme-specific/legacy pieces:

- `SummaryConfig(S0/S1/S2/S3/R0)`;
- summary-first routing interfaces;
- assumption that all remote knowledge becomes `usable_edges()`;
- laminar-only LocatorCatalog;
- Phase-number-driven experiment runner;
- D0/D1 decomposition as the primary research axis;
- normalized-scalar state as cross-scheme comparison.

## 12. Dynamic/control-plane reconciliation

Do not invent a generic new distributed shortest-path convergence algorithm.

Relevant established baselines include:

- Bellman-Ford / distance-vector;
- DUAL/diffusing computations for loop-free dynamic routing;
- distributed compact-routing/table construction in small-message models;
- dynamic approximate routing schemes;
- fault-tolerant compact routing and fault-tolerant spanners/labels.

NetSynth's residual questions are:

- who owns which theoretical state;
- what must be replicated;
- how routing-label changes invalidate Rendezvous/Channel state;
- how many bits/messages cross each locality boundary;
- whether recursive/overlapping structures can be maintained without global recomputation;
- profile-specific constants.

## 13. Immediate research consequences

Before implementing another architecture phase:

1. finish the compact-routing theory map;
2. define the generic routing-scheme/resource model;
3. decide whether Routing Descriptor replaces Locator in the common architecture;
4. decide whether Channel explicitly supports handshake-derived routing context;
5. refactor the simulator only after these semantics stabilize;
6. then implement established baseline schemes before inventing new ones.

The next implementation should be a **research-framework refactor**, not Phase 6 metric repair.
