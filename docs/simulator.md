# NetSynth Simulator Plan

> Status: implementation target for the first coding phase.
>
> The simulator exists to falsify or constrain architecture hypotheses. It must not silently turn implementation convenience into architectural truth.

## 1. First question

The first simulator phase evaluates the current Routing Scope / Structured Locator hypothesis:

> Can recursive topology compression reduce per-node routing state and failure propagation without causing unacceptable path stretch?

The simulator is not yet a packet-level Internet simulator and is not intended to reproduce Ethernet/IP/TCP behavior.

## 2. Required model

The first implementation needs only:

- a graph of forwarding nodes and links;
- configurable link cost/capacity metadata, even if early experiments use unit cost;
- one or more topology generators/importers;
- a baseline flat-routing model;
- a scope decomposition representation;
- a quotient-graph representation for each compression level;
- route computation for baseline and compressed architectures;
- controlled topology-change events;
- metrics and reproducible experiment output.

Do not implement Endpoint ID, Rendezvous, Channel, transport, security, wireless, or application traffic in phase 1.

## 3. Baselines

At minimum compare:

### Flat full-knowledge baseline

Each routing node knows the graph at full resolution and routes on the uncompressed topology. This gives a lower-bound reference for path length and an upper-style reference for globally replicated topology state.

### Recursive scope compression

The same physical graph is partitioned recursively where useful. Nodes retain detailed local knowledge and progressively coarser remote knowledge.

The first implementation may use an intentionally simple/manual partitioning mechanism. Scope-formation optimization is a later experiment; do not block the simulator on finding an ideal clustering algorithm.

## 4. Primary metrics

The first phase must report these four metrics clearly.

### 4.1 Routing State

Measure at least:

- per-node forwarding/routing entries;
- mean, median, p95, p99, and max state;
- total state across the network;
- state broken down by local-detail vs aggregate entries where meaningful.

Avoid claiming O(log N) from a few empirical points. Report measured scaling first.

### 4.2 Path Stretch

For source/destination pairs:

```
stretch = compressed_route_cost / shortest_path_cost
```

Report mean, p50, p95, p99, and max stretch, plus the fraction of routes with stretch exactly 1.

Route cost should initially support unit hop count and later weighted links.

### 4.3 Churn

For a topology event such as one link failure/recovery, measure:

- number of routing/control objects that must change;
- number/fraction of nodes whose forwarding state changes;
- amount of aggregate state invalidated or recomputed;
- scope levels reached by the change.

Do not equate simulator CPU work with protocol control traffic unless an explicit propagation model has been implemented.

### 4.4 Failure Locality

Measure how far a local failure escapes its containing scopes.

Examples:

- absorbed entirely inside the smallest scope;
- changes the smallest scope's external summary;
- propagates to parent/grandparent/global scope.

Report a distribution over many failure locations, not only selected examples.

## 5. Secondary metrics

Useful once the first four work:

- boundary size per scope;
- internal-node/boundary ratio;
- quotient graph size per level;
- hierarchy depth distribution;
- routing computation work;
- locator depth distribution;
- route diversity / number of eligible next hops;
- sensitivity to scope restructuring.

These are secondary until the core metrics are trustworthy.

## 6. Topology families

Experiments should cover structurally different graph families rather than one Internet-like topology.

Suggested initial set:

1. **Tree / hierarchical tree-like graphs** — favorable case for aggregation.
2. **Fat-tree / Clos-like graphs** — regular datacenter-style multipath topology.
3. **2-D/3-D mesh or torus-like graphs** — local geometric structure with many alternate paths.
4. **Random geometric graphs** — locality-driven but irregular.
5. **Small-world graphs** — strong local clusters plus sparse long-range shortcuts.
6. **Erdos-Renyi/random graphs** — generic irregular baseline.
7. **Expander-like/high-conductance graphs** — deliberate hostile case for hierarchical compression.

The purpose is not to prove one decomposition works everywhere. A valuable result may be identifying graph families where compression fundamentally performs poorly.

## 7. Scale progression

Do not jump directly to 1e8 nodes.

Start with sizes that allow exhaustive shortest-path validation, for example:

```
10^2 -> 10^3 -> 10^4
```

Then scale only after correctness and metric definitions are stable.

Large-scale experiments may use sampling rather than all-pairs shortest paths, but the simulator must make that explicit in output metadata.

## 8. Scope decomposition interface

Treat scope decomposition as an interchangeable strategy.

Conceptually the simulator should accept something like:

```
decompose(G) -> ScopeTree / MultiResolutionGraph
```

The exact API is an implementation detail, but architecture experiments must be able to swap strategies without rewriting the routing core.

Early strategies may include:

- manually generated hierarchy matching the topology generator;
- balanced graph partitioning;
- separator/community-based recursive partitioning;
- deliberately bad/random partitioning as a control.

Do not hard-code geographic, provider, country, rack, AS, or administrative meanings into a scope.

## 9. Routing under compression

The simulator should preserve this architectural distinction:

- physical connectivity is an arbitrary graph;
- scope membership is a laminar compression hierarchy in the current hypothesis;
- routing is not constrained to follow the hierarchy as a tree;
- quotient graphs may contain cross-links between sibling scopes;
- within a scope, internal routing may use detailed topology;
- outside a scope, only summarized/aggregate knowledge should be charged to remote routing state.

The first version may implement a conservative recursive route construction. More sophisticated boundary summaries can be added as separate experiments.

## 10. Failure experiments

At minimum support:

- single link down/up;
- single forwarding node down/up;
- random sets of independent link failures;
- boundary-link failure vs internal-link failure.

For each event, compare flat and compressed architectures using the same physical graph.

A local failure that does not change a scope's externally visible reachability should ideally remain inside that scope. The simulator should make violations visible rather than assuming containment.

## 11. Reproducibility

Every experiment output should record enough information to reproduce it:

- topology family;
- node/link counts;
- generator parameters;
- random seed;
- decomposition strategy and parameters;
- routing strategy and parameters;
- sampled source/destination count if not exhaustive;
- failure event definition;
- metric version/schema.

Machine-readable output is required. Human-readable summaries are useful but secondary.

## 12. Non-goals for phase 1

Do not add these merely because a traditional network simulator would have them:

- MAC addresses;
- IP addresses or subnets;
- TCP/UDP/QUIC;
- ports;
- DNS;
- BGP/OSPF/IS-IS emulation;
- packet serialization timing;
- queues and congestion control;
- security;
- wireless models;
- endpoint mobility;
- rendezvous;
- full packet wire formats.

They can be introduced later only when a specific architectural question requires them.

## 13. Phase-1 exit criteria

Phase 1 is useful when it can answer, with reproducible evidence:

1. How much routing state does recursive compression save on each topology family?
2. What path stretch does that compression introduce?
3. How many nodes/state objects change after a local failure?
4. At what scope level does a failure stop propagating?
5. On which topology families does the current hypothesis fail badly?

A negative result is acceptable and valuable. The simulator exists to expose architectural mistakes early.
