# NetSynth Research-Value Gate: First Adversarial Derivation

> Status: research critique, 2026-10-08. This is NOT a revision to the frozen v0.1 semantic architecture.
>
> Decision at this stage: Do not commence the XDP implementation or a broad simulator rewrite. First determine whether NetSynth has a useful remaining theoretical or systems delta against a best-effort strong baseline.

## Mandatory reconciliation header

Mathematical abstraction:
- Dynamic graph routing under partial/topology-summary knowledge.
- Fault-tolerant terminal reachability and approximate terminal metrics.
- Multi-timescale state placement: persistent forwarding entries, packet bytes, control updates, program compilation and repair.
- Online or time-coupled optimization with switching costs and constrained local information.

Closest established problems:
- Hierarchical dynamic routing and adaptability, topology aggregation, pathlet routing, SR Policies / Binding SIDs.
- Optimal path encoding and compact routing.
- Fault-tolerant distance preservers and robust route planning.
- Reconfiguration-limited SR traffic engineering.

Known upper bounds / constructions:
- Dynamic hierarchical routing constructions (Bubbles);
- OSPF area knowledge isolation;
- area-based pathlet control plane with advertised boundary-to-boundary pathlets;
- Segment Routing Binding SID and local policy switching;
- path encoding approximation;
- fault-tolerant terminal preservers in applicable graph/failure models.

Known lower bounds / impossibility:
- Compact routing imposes table-space / header / stretch trade-offs, with model-specific conditions.
- Fault-tolerant distance-preserving structures can have high state cost.
- In this note, a small two-state indistinguishability construction shows that preserving only reachability while hiding all metric changes cannot guarantee bounded stretch.
- Existing optimal path encoding is APX-hard; do not assume a universally optimal simple compiler.

Why these results do not fully answer NetSynth:
- They do not by themselves choose a fair, end-to-end benchmark objective across the exact frozen v0.1 ownership, packet budget, repair and route-cache semantics.
- However, that does NOT establish originality. The model may be expressible through established methods.

NetSynth-specific question:
- Under precisely matched capabilities, can selecting the strength of boundary transit commitments and their resource budget reduce long-run externally visible state changes without paying an equal or greater cost in route quality, preinstalled state or packet overhead?

Minimal experiment required:
- None before the small analytical counterexamples and expressiveness comparison below.
- After a concrete residual hypothesis is formulated, at most one small adversarial dynamic fixture with a hierarchical SR/BSID-like baseline. No broad sweeps.

## 1. Closest prior art: the collision is severe

### Hierarchical routing and topology aggregation

OSPF areas already isolate interior topologies and routing knowledge. The 1999 Bubbles routing work constructs dynamic hierarchical partitions and analyzes the number of node updates after changes, including optimality under its bounded-degree network model.

Thus local update containment is not new, and should not be benchmarked only against an intentionally flat link-state network.

Sources:
- https://www.rfc-editor.org/rfc/rfc2178.html
- https://epubs.siam.org/doi/10.1137/S0097539797316610

### Pathlet routing: effectively the same architecture skeleton

Godfrey et al. (SIGCOMM 2009) introduce composable source-path fragments.

Chiesa et al. (Computer Communications 2014), Intra-domain routing with pathlets, goes further: routers are grouped into areas, local topology is retained inside each area, and the exterior sees a single pathlet from entry to exit rather than internal path decisions. It studies robust and independent area control.

This is a striking functional overlap with NetSynth Scope / BTG / STP, not merely a superficial conceptual resemblance.

Sources:
- https://experts.illinois.edu/en/publications/pathlet-routing/
- https://www.sciencedirect.com/science/article/abs/pii/S0140366414000978

### Binding SID: local change without upstream state changes

RFC 8402 section 5 explicitly states that when a policy bound to a BSID changes, only policy-imposing nodes need updates; users of that policy are not impacted.

RFC 9256 section 6 describes a BSID kept across active candidate-path changes.

Therefore STP-repair-with-unchanged-external-token is a known mechanism, not by itself a differentiator.

Sources:
- https://www.rfc-editor.org/rfc/rfc8402
- https://www.rfc-editor.org/rfc/rfc9256

### Encoding and reconfiguration optimization

Hari, Niesen and Wilfong establish hardness and approximation results for reusable forwarding-state path encoding.

A preprint submitted October 3, 2026, Segment Routing Traffic Engineering with Time-Based Reconfiguration Constraints, explicitly jointly studies route quality, segment/configuration complexity and configuration changes over time.

Thus merely writing one joint weighted objective is not original.

Sources:
- https://arxiv.org/abs/1507.07217
- https://arxiv.org/abs/2610.04759

### Fault-tolerant route quality

Fault-tolerant distance preservers/spanners already study the amount of state needed to preserve terminal distances despite failures.

Source:
- https://drops.dagstuhl.de/entities/document/10.4230/LIPIcs.ICALP.2017.73

## 2. Comparison equivalence warning

Consider a best-effort baseline with:

- hierarchical topology/knowledge ownership;
- local policy controllers;
- programmable short BSIDs or equivalent local forwarding tokens;
- a path computation element;
- budgeted packet- and table-resident route state.

Each NetSynth STP can be modeled conceptually as a local policy exposed by a BSID, and a parent route can compose such policies. On internal repair, only the local policy realization changes.

This is a constructive similarity argument, NOT a proven production-level, byte-for-byte emulation and NOT a theorem that every deployed SR configuration provides every NetSynth semantic.

The implication is narrower but important:

> A measured advantage over flat OSPF, conventional shortest-path IP or single-path TCP does not establish an architectural advantage over the strongest existing composition of these ideas.

The baseline must be afforded the same ability to place information in packets/local tables and the same control hierarchy; only true extra constraints of a real deployment should count as compatibility taxes.

## 3. Formal dynamic problem

Let G_t=(V,E_t,w_t) be a physical graph at observation period t.

Let D_t contain source-destination demands and byte/packet volumes.

A solution chooses:
- H_t: a control/ownership hierarchy or flat representation;
- K_t: boundary-to-boundary contracts and their advertised guarantees;
- F_t: installed reusable forwarding entries;
- P_{d,t}: compiled per-demand packet route state;
- R_t: physical realizations inside each owner.

Feasibility includes:
- owner-visible-only composition;
- physical route continuity;
- STP exact-generation semantics;
- no in-flight packet enlargement;
- declared packet and forwarding-context capacities;
- forwarding state and update budgets;
- acceptable route quality / demand satisfaction.

A broad cost accounting can be written:

~~~text
C = sum_t (
    a * installed_state_bytes(t)
  + b * packet_route_bytes_transmitted(t)
  + c * control_update_bytes_and_work(t)
  + d * path_excess_cost(t)
  + e * repair_failure_or_outage_cost(t)
  + f * restructuring_and_compilation_work(t)
)
~~~

This is only an accounting framework, not an alleged new algorithm.

Do not choose arbitrary weights and claim a universal win. First compare Pareto fronts or minimize a single metric subject to matched hard constraints, such as:

~~~text
minimize expected external control-update traffic

subject to:
    route stretch <= rho
    installed state <= M
    route code <= H
    forwarding context <= W
    maximum acceptable failure rate <= epsilon
~~~

Weights/capacities must be applied identically to NetSynth and strong baselines.

## 4. Analytical counterexample A: hidden repair versus route quality

Consider a parent routing from boundary a to boundary b.

It can choose:
- an internally opaque STP S;
- an external bypass E.

The bypass cost is R, for arbitrary R > 1.

There are two internal network states:

~~~text
                   state G0         state G1
S internal cost        1               R^2
E bypass cost          R               R
S reachable?          yes             yes
~~~

Interpret G1 as a failed cheap internal link, leaving a still-reachable but expensive backup inside S.

Suppose the parent sees only the SAME binary reachability contract in both states, gets no metric update, and cannot inspect the hidden topology.

Then it must make the same route choice in both states (assuming fixed deterministic policy and no other distinguishing signal):

- choose S in both: cost ratio in G1 is R^2 / R = R;
- choose E in both: cost ratio in G0 is R / 1 = R.

Thus worst-case stretch is at least R. Since R can be arbitrarily large, no constant stretch guarantee follows from a reachability-only stable summary.

This is a simple NetSynth-specific indistinguishability counterexample, not a novel compact-routing lower bound.

Crucial nuance: NetSynth distinguishes hard STP generations from soft metrics. It CAN propagate a soft metric update and keep the hard generation intact. But then one cannot score that event as 'zero external control cost' merely because zero hard generations changed.

Conclusion:

> Hiding hard failure propagation does not imply zero control propagation or preserved route quality.

## 5. Analytical counterexample B: trivial convergence with a strong BSID baseline

Suppose S has two internally disjoint a-to-b paths, and the primary fails.

NetSynth:
- maintain same STP generation and external token;
- update S's local forwarding realization;
- no parent hard update.

A hierarchical SR / Binding-SID-like solution:
- maintain the same exposed BSID for the policy;
- switch active local candidate path;
- no upstream BSID user update.

On the specific metric of external hard-token changes, the two mechanisms tie.

Therefore the toy argument 'a ring has zero hard export changes' DOES NOT establish an advantage over strong modern routing.

## 6. Analytical counterexample C: structural noncompressibility

Consider a region with numerous physical crossings to other regions or a topology for which many boundary-to-boundary costs are important and vary independently.

A Scope cannot guarantee small state, small packet route code and near-exact arbitrary routing simply by adding hierarchy.

Options are:
- export/retain more transit information;
- expose less information and permit path-quality degradation;
- keep the region flat;
- change the feasible route or service guarantees.

These are established graph decomposition and compact routing limitations.

NetSynth's flat fallback is good engineering, but not a general compression theorem.

## 7. A more precise residual research question: the strength of a contract

Reachability-only contracts are too weak to guarantee path quality.

A possible stronger owner-local boundary contract is:

~~~text
Contract(a,b):
    hard: exact endpoints and generation
    hard: maximum packet execution resource budget
    conditional: local failure family supported
    optional promise: transit cost <= U
    soft: current observed cost estimate
~~~

The first two hard fields are compatible with frozen v0.1; the others are only research candidates, NOT newly adopted architectural fields.

A stable cost upper bound U gives a meaningful planning promise but creates a tradeoff:

- small U: better parent route choices, but local repairs more often violate contract;
- large U: more repairs stay hidden, but parent may avoid good internal routes;
- soft updates: better decisions but consume externally visible control traffic;
- a larger supported failure family: more preinstalled fallback information or route slack may be needed.

Example based on counterexample A:
- with U < R^2, state G1 breaks the performance promise and requires an update/new suitable contract;
- with U >= R^2, the parent can treat S as robustly reachable but cannot infer its cheap current route from U alone;
- with U as an upper bound plus soft current cost, the parent may route better but must decide when the soft information deserves propagation.

There is a nontrivial cost/quality/freshness frontier here.

However, robust topology abstraction, QoS topology aggregation and fault-tolerant distance preservers are longstanding work; this contract is not yet an original contribution.

## 8. More precise hypothesis, not a novelty claim

Hypothesis H:

> For changing graphs with heterogeneous failure probabilities and routing demands, jointly choosing the boundary guarantee strength, local reserve resources and external update policy can reduce long-run update cost under strict stretch/packet/state budgets compared with a controller that optimizes paths or encoding alone.

This hypothesis may be false, and recent SR time-coupled optimization may already subsume much of it.

Before implementation, determine whether published topology-aggregation / fault-tolerant TE / PCE work already studies this exact optimization.

Avoid merely placing a new term in a weighted sum.

## 9. Minimal falsification gate

Use two domains joined by both:
- one Scope-internal opaque transit route, whose cost changes after an internal fault;
- one globally visible bypass route.

Give all methods the exact same graph, time sequence, failure signals, route-quality constraint, packet/context capacity and local table budget.

Methods:
- NetSynth frozen v0.1 with specified boundary contract and soft update policy;
- hierarchical SR / BSID with a PCE allowed to use the same owner-local topology and install local repair entries;
- an ideal optimizer in the same feasible set (small-instance exhaustive dynamic program only if useful).

For each, count:
- physical delivery and route cost;
- all hard AND soft control updates;
- installed state in ALL owners;
- header bytes per packet;
- compilation/installation changes;
- parent and ingress activity;
- failure during in-flight packet transition.

Tests must include:
1. internally redundant cheap repair;
2. internally redundant but very expensive repair;
3. no internal backup;
4. two interacting Scopes with competing external bypasses;
5. a noncompressible region.

A single simple graph is enough to establish an impossibility or counterexample. Do not scale or optimize unless it reveals a genuine residual.

## 10. Current assessment and next decision

Findings:

- The NetSynth v0.1 design remains internally coherent.
- Its routing skeleton and strongest advertised properties substantially overlap mature proposals.
- Binary hard-contract preservation is insufficient evidence of low control cost or good route quality.
- The selected dynamic optimization question is not yet verified to be original.
- Small analytical counterexamples already prohibit unconditional 'best of all worlds' claims.

Recommendation:

1. Keep v0.1 frozen as an architectural reference, not as a validated research contribution.
2. Pause full-stack / XDP implementation and large simulator refactoring.
3. Research the narrower guaranteed-cost / controlled-freshness contract problem against strong topology aggregation, BSID/PCE and dynamic TE prior art.
4. Only if a credible delta survives, write a minimal checker or theorem; otherwise pivot research rather than expanding NetSynth features.

Research-value gate:

~~~text
If the strongest prior-art baseline can implement the same contract
with comparable resource costs and guarantees,
do not claim a new architecture advantage.

If no separation survives, either:
    preserve NetSynth as a clean systems synthesis exercise, or
    select a genuinely different unsolved networking question.
~~~

## Sources

- RFC 2178 OSPF area isolation: https://www.rfc-editor.org/rfc/rfc2178.html
- Bubbles (dynamic hierarchical routing): https://epubs.siam.org/doi/10.1137/S0097539797316610
- Pathlet Routing (SIGCOMM 2009): https://experts.illinois.edu/en/publications/pathlet-routing/
- Intra-domain routing with pathlets (2014): https://www.sciencedirect.com/science/article/abs/pii/S0140366414000978
- RFC 8402 Binding Segment: https://www.rfc-editor.org/rfc/rfc8402
- RFC 9256 Segment Routing Policy: https://www.rfc-editor.org/rfc/rfc9256
- RFC 9604 PCE Binding SID support: https://www.rfc-editor.org/rfc/rfc9604
- Optimal Path Encoding: https://arxiv.org/abs/1507.07217
- Reconfiguration-limited SR-TE (2026-10-03 preprint): https://arxiv.org/abs/2610.04759
- Topology aggregation survey: https://experts.illinois.edu/en/publications/analysis-of-topology-aggregation-techniques-for-qos-routing
- Fault-tolerant distance preservers: https://drops.dagstuhl.de/entities/document/10.4230/LIPIcs.ICALP.2017.73
