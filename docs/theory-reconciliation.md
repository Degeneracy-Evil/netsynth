# NetSynth Theory Reconciliation

> Status: mandatory mathematical baseline before any new architecture phase.
>
> NetSynth remains a clean-slate architecture project. "Clean slate" means no inherited protocol semantics or compatibility obligations. It does **not** mean ignoring established graph theory, routing theory, distributed algorithms, metric geometry, or lower bounds.

## 1. Corrected research stance

The project should separate two kinds of inherited knowledge:

- **Protocol/history assumptions** — Ethernet, IP, TCP, BGP, DNS, AS semantics, fixed address formats, and compatibility constraints are not default premises.
- **Mathematical results** — compact routing, spanners, emulators, distance oracles, metric embeddings, sparse covers, separators, distributed shortest-path algorithms, labeling schemes, and lower bounds are reusable foundations.

Once a NetSynth question reduces to a mature mathematical model, use the strongest applicable theorem/construction first. Do not rediscover its asymptotic behavior with simulator sweeps.

Simulation is reserved for the delta between the mathematical model and NetSynth's actual architecture semantics.

## 2. Phase-by-phase reconciliation

### Phase 1 — recursive Scope compression

**NetSynth question:** can hierarchical topology compression trade routing state for path stretch and localize updates?

**Established theory:** hierarchical routing and compact routing have studied this trade-off for decades. Kleinrock–Kamoun already studied hierarchical clustering versus routing-table length/path length. Awerbuch–Peleg sparse covers and later compact-routing work give general hierarchical constructions and communication-space/stretch trade-offs. Thorup–Zwick and successors give near-optimal compact-routing state/stretch trade-offs for general weighted graphs.

**What was duplicated:** treating the existence of a state/stretch frontier for arbitrary graphs as an open empirical question.

**What remains useful:** NetSynth's accounting of *where* state is owned, how summaries compose recursively, and how failures/updates propagate across scopes.

### Phase 2 — S0/S1/S2/S3 summaries

**S2 landmarks:** closely overlaps landmark-based compact routing and distance-oracle constructions, especially Cowen/Thorup–Zwick style balls, clusters, pivots, and hierarchies.

**S3 full boundary matrix:** is a terminal-distance representation. Its quadratic boundary cost is part of the mature terminal-metric compression / distance-preserver / emulator literature.

**What was duplicated:** ad-hoc sweeps asking whether more landmarks can improve stretch and observing that exact boundary metrics can become expensive.

**What remains useful:** whether a summary representation is recursively composable under NetSynth ownership rules, and the control-state/churn cost of deploying a known construction.

### Phase 3 — Structured Locator and knowledge-disciplined forwarding

**Structured Locator:** belongs to the **name-dependent compact-routing / routing-labeling** world: the routing architecture is allowed to assign topology-dependent labels.

**Endpoint ID vs Locator:** maps naturally to the distinction between name-independent and name-dependent routing. Classical name-independent routing proves that arbitrary stable names can be routed compactly, but at different space/stretch/header costs.

NetSynth's two-stage idea is therefore not "identity and location must be separated because mathematics says so"; rather, it is an architecture choice:

```text
stable Endpoint ID
    --cold-path resolution-->
topology-dependent routing Locator
    --hot-path compact routing-->
destination
```

This must eventually be compared against direct name-independent compact-routing schemes.

**Useful Phase-3 finding:** the simulator exposed a hidden remote-path oracle. That is architecture-semantic validation, not a new routing theorem.

### Phase 3.1 — R0 reachability summary

For an undirected Scope, exact boundary reachability is simply the connected-component equivalence relation on boundary terminals and can be represented linearly in the number of interfaces. Sparse connectivity certificates and reachability-preserver theory are stronger surrounding results.

**What was duplicated:** treating linear-size preservation of static undirected connectivity as a novel compression result.

**What remains useful:** testing interface closure and validating that a concrete recursive summary implementation does not accidentally destroy reachability.

### Phase 3.2 — scoped potentials

The mathematical core is classical distance-vector / Bellman–Ford reasoning. Strictly decreasing destination potential gives an acyclic forwarding relation after convergence; loop-free distributed shortest-path routing under changing metrics has mature work, notably diffusing computations / DUAL and feasibility conditions.

**What was duplicated:** using simulation to establish the converged loop-free property of strict potential descent.

**What remains useful:** NetSynth's unusual destination keys are *aggregate topology prefixes*, not ordinary individual destinations. The state/update cost and ownership of scoped aggregate potentials remain architecture questions.

Future transient/asynchronous work must start from established loop-free distance-vector theory rather than invent a new convergence protocol.

### Phase 4 — attachment lookahead

Increasing lookahead exposes progressively more destination-specific metric information. This is another form of the classical routing-label / routing-table / stretch trade-off.

**What was duplicated:** treating generic "more destination-specific information reduces stretch while increasing state" as a discovery.

**What remains useful:** the exact NetSynth prefix-monotone forwarding semantics and the distinction:

```text
information stretch
vs
hierarchy-constraint stretch
```

The finite h=1/2/3 experiments are implementation/constant-factor probes, not general mathematical evidence.

### Phase 5 — metric-aware decomposition

Sparse covers, network decompositions, separators, metric decompositions, distance labeling, and tree/metric embeddings already explain much of the observed family dependence.

- Planar graphs have O(sqrt(n)) balanced separators.
- More generally, minor-restricted families admit sublinear separators.
- Expanders have no small balanced separators by definition/expansion, and random regular graphs are expanders with high probability.
- FRT shows arbitrary metrics admit O(log n)-expected dominating tree embeddings and that logarithmic tree distortion is unavoidable for some metrics.

NetSynth's hierarchy is richer than a pure tree metric, so FRT is not a direct lower bound on the current architecture. However, it is a warning against expecting universally low-distortion hierarchy for arbitrary metrics.

**Model-specific useful lemma:** under NetSynth's full-attachment, prefix-monotone semantics, Scope isometry is the exact zero-hierarchy-stretch endpoint. That is a useful architectural characterization, but the surrounding distortion/compression phenomenon is classical.

**What was duplicated:** brute-force decomposition experiments as if "mesh/tree easy, expander/random hostile" were unknown.

**What remains useful:** measuring how a standard/theoretically justified decomposition behaves under NetSynth's exact state ownership, Locator depth, update locality, and forwarding semantics.

## 3. Phase 6 reconciliation

The previous Phase-6 document proposed sparse external boundary-to-boundary shortcuts and a quantity `R_epsilon(S)`.

Do **not** treat `R_epsilon(S)` as a new mathematical object without additional NetSynth-specific constraints.

Let `B(S)` be a Scope's boundary terminals. The static mathematical core is already covered by several standard models:

### Terminal metric / emulator view

The complete weighted graph on `B(S)` with edge weights equal to external shortest-path distances is the exact terminal metric closure.

If virtual weighted edges are allowed, sparsifying that closure is a **metric spanner / emulator** problem.

For arbitrary metrics, classical multiplicative spanner results give a `(2k-1)`-spanner with about `O(|B|^(1+1/k))` edges. Conversely, near-exact preservation cannot generally remain sparse; even the equilateral metric forces all terminal-pair edges for stretch strictly below 2.

### Pairwise/subsetwise spanner view

If only selected boundary pairs matter, this is a **pairwise spanner** problem.

If all pairs in the boundary terminal set matter, it is **subsetwise spanner** territory.

If distances must be exact and the representation must be a subgraph of the original graph, this becomes a **distance preserver** problem.

### Terminal compression / vertex sparsifier view

If the external region itself is to be replaced by a smaller graph over its terminals, this is a **terminal distance sparsifier / distance-preserving minor / Steiner-point-removal** problem, depending on whether exactness, minor structure, or approximation is required.

Known exact distance-preserving-minor results already show nontrivial polynomial upper bounds and quadratic lower bounds in the terminal count, with stronger special-family results.

### Hopset view

A hopset is relevant only if the objective also constrains the number of hops used by the approximate path.

Phase 6's original primary objective was state/stretch of boundary metric repair, so **hopset is related but not the closest abstraction** unless NetSynth starts optimizing transit hop count or distributed computation rounds.

### Minimum-spanner hardness

If Phase 6 asks for the *minimum* number of shortcuts that achieves a prescribed stretch, it enters minimum/sparsest spanner optimization, which is computationally hard in general. A brute-force greedy selector must therefore be described as a heuristic/research oracle, not as unexplored architecture theory.

## 4. What is actually NetSynth-specific in a future "metric repair" phase

The mathematical static representation is mostly known.

The architecture-specific delta is:

1. a virtual emulator/spanner edge must be **realized hop-by-hop** over the physical graph;
2. the realization must use only locally owned state;
3. virtual edges must compose recursively with Scope summaries;
4. packet/header state used to realize them must be explicitly bounded and charged;
5. updates/failures should ideally invalidate only local portions of the representation;
6. state ownership and replication are architecture decisions, whereas a graph-theory theorem usually counts only total edges/bits;
7. the representation must coexist with topology-dependent Locators and progressive-resolution forwarding.

This is where future simulator work can add information rather than rediscovering spanner theory.

## 5. Experiments to stop

Do not spend simulator time primarily to establish any of the following generic facts:

- arbitrary-graph compact routing has a state/stretch trade-off;
- stretch approaches exactness only by paying more metric information;
- landmarks can trade state for approximate distance;
- exact all-boundary metrics may be quadratic;
- trees are easy to route compactly;
- planar/geometric graphs tend to have better separators than expanders;
- expanders are hostile to low-boundary hierarchy;
- strict potential descent is loop-free after convergence;
- more destination-specific information can reduce stretch;
- minimum low-stretch sparsification is computationally hard.

These should enter the project as cited theory, not experimental discoveries.

## 6. Experiments that remain valuable

Simulation remains useful for quantities not captured by the standard asymptotic models:

- **architecture state accounting:** data-plane FIB, control summaries, Locator references, virtual-edge realization state, replication/ownership;
- **update locality and churn:** changed objects, changed owners, Scope levels reached;
- **NetSynth-specific headers/context:** destination Locator plus bounded temporary transit state;
- **recursive composability:** whether a theoretical structure can be constructed from child summaries rather than hidden global topology;
- **realization semantics:** whether emulator edges can be executed by legal physical next hops;
- **profile constants:** datacenter/HPC, general wired, constrained/IoT;
- **failure behavior:** while comparing against existing fault-tolerant compact-routing theory;
- **dynamic/asynchronous behavior:** while starting from DUAL/diffusing-computation and dynamic-routing results rather than inventing convergence from scratch.

## 7. The real architecture question

NetSynth should no longer ask:

> Can routing on arbitrary graphs be compact?

That question is already deeply studied.

A more precise NetSynth question is:

> Can we build a dynamic, recursively composable, topology-labeled compact-routing architecture in which stable endpoint identity is resolved off the forwarding hot path to mutable topology-dependent labels; each node owns only local detail plus bounded multiresolution state; virtual metric-compression edges are realizable with small bounded packet context; and topology changes have explicitly local update/churn behavior, while matching known static compact-routing/spanner bounds closely enough to be practical?

The mathematical components are established individually. The research value lies in their **architectural composition and operational semantics**, not in renaming the individual graph primitives.

## 8. Required theory baselines going forward

Before any next Phase, explicitly compare against relevant results from:

- compact routing and routing labeling;
- name-dependent/name-independent routing;
- spanners, pairwise/subsetwise spanners, emulators, distance preservers;
- distance oracles and terminal distance sparsification;
- hopsets when hop count matters;
- sparse neighborhood covers and graph decompositions;
- metric/tree embeddings;
- separators, expansion, treewidth/minor structure;
- distributed shortest paths and loop-free distance-vector algorithms;
- connectivity/reachability certificates and fault-tolerant routing;
- dynamic compact routing / dynamic distance structures when topology changes are central.

The simulator should then test only the residual NetSynth-specific gap.
