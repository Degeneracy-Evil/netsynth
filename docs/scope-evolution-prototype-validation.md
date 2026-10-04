# Structural-control minimal semantic validation

## Reconciliation and scope

Mathematical abstraction: local versioned ownership partitions, generation-safe references, make-before-break
renumbering, and amortized control-state benefit versus structural movement/rebuild cost.

Closest established problems: network renumbering, identifier/locator separation, consistent updates and
dynamic partitioning with migration costs. [RFC 4192](https://www.rfc-editor.org/rfc/rfc4192) supplies the
make-before-break procedural comparison, not inherited address/protocol semantics.

Known constructions / upper bounds: reuse frozen object generations, exact owner-local transit realization,
opaque child summaries and existing multi-Locator bindings. No new partition construction is proposed.

Known lower bounds / impossibility: arbitrary graphs need not have small useful separators; a partition
cannot guarantee universal summary compression. Partition optimality/approximation is not investigated.

Why existing theory does not fully answer NetSynth: the residual question is layout/object lifetime,
ownership visibility, parent hard-contract containment and explicit renumbering cost, not separator quality.

NetSynth-specific question: can local restructuring preserve identity/routing semantics while honestly
charging persistent state and refusing an unhelpful hierarchy?

Minimal experiment: only a ten-node two-clique/one-bridge modular graph and a six-node complete weighted
graph. Each has a hand-selected flat layout and a connected two-child split. The latter also merges back
to a fresh flat generation. No partition search, scaling, stretch or congestion benchmark is run.

## Implementation

`scope_evolution.py` adds a stable `RoutingScope`, with at most two prepared/active layouts and a single
monotonic Scope-local generation floor. Each layout validates connected, disjoint exact child coverage
using existing `ScopeTree`. Two active layouts may overlap; membership within either layout cannot.

Locators use existing `Locator` objects. Fixture components are `(stable Scope prefix, local layout
generation, child label)` and an owner-local selector. This is a semantic encoding choice, not a wire
format or global epoch. Child pathlet owners and query identities are also generation-qualified. Tests
reuse child label/selector zero for different physical positions and verify that old meanings cannot alias.

Construction accepts exactly the declared Scope-local graph, not a full external graph. Membership belongs
to the structural ownership controller. Leaf owners receive induced local graphs; only they realize leaf
STPs/Access offers. Runtime Route Services still see only immediate-child BTGs, boundary ownership and
crossings. The fixture orchestrates owner-local query calls; it is not a parent remote-topology oracle.
Tests disable detailed/global graph planners while parent activation/resolution continues to work.

Prepare builds privately; activation enables new Locator queries without disabling old ones. Two local
Endpoints publish old+new Locator sets, then new-only bindings, totaling four transition publications.
The same EID-bound Channel, tokens, number spaces, reliability and receive credit survive path replacement.

Retirement clears old owner-local query maps and retires old child STPs. Cached frozen-executor Access
views therefore fail with `missing_access_state`, cached child handles with `stale_pathlet`, and the local
layout entry gate with `stale_layout`. Fresh generations cannot reuse retired generation numbers.

Stable exported Scope hard contracts rebind to a newly validated owner view: selected-layout crossings
and immediate-child STPs only. No generation change is made to a preserved external contract. Rebinding
is allowed only while the exact exported slots are still live; withdrawing a slot cannot be undone by
layout activation. The prototype deliberately supports a fixed exported contract set, not arbitrary
hard-contract allocation or a new control protocol. Cached parent **transit segments** keep executing
through the new internal realization after the old layout retires. This is not delivery to a stale endpoint
Locator (the frozen pathlet-only program-completion caveat still applies).

## Budget and policy choices

All metrics are declared normalized records, not Python heap bytes or asymptotic bounds:

- owner-local topology nodes/links, ownership metadata, Route-Service state, registry realization state
  and per-slot generation watermarks;
- pushed child boundary/BTG records and externally exported Scope boundary/BTG records;
- hard advertisement/interface additions/withdrawals, excluding soft metric updates;
- new control-state rebuild, every changed attachment Locator, two Binding publications per affected EID,
  and conservative old+new overlap state.

Flat means one unsplit local region. Its leaf/service views are colocated, and their actual stored records
are charged rather than declaring prototype wrappers free. Stable fixed owner metadata and query-local
Access records are not silently interpreted as topology summaries; query Access records are reported
separately. Overlap is a conservative staging peak, not steady-state state reduction.

The fixture-only policy uses `peak controller + total local state + parent-visible records + 4 * hard updates`.
It requires gain >= 5 for three observations, and a 20-observation expected benefit exceeding transition
cost plus margin 20. All values/weights are in JSON; none is an architectural constant or universal scalar
objective. Short-lived or one-record improvements fail hysteresis/benefit gates; a short horizon fails
the migration-cost gate. No automatic traffic-demand optimizer is introduced.

## Results

| Topology / layout | Controller peak | Total local state | External Scope BTG | Child boundary / STPs |
| --- | ---: | ---: | ---: | ---: |
| Modular flat | 67 | 67 | 4 | 2 / 2 |
| Modular split | 36 | 80 | 4 | 4 / 4 |
| Dense flat | 49 | 49 | 4 | 2 / 2 |
| Dense split | 46 | 96 | 4 | 6 / 12 |

The modular split is accepted: substantial controller relief outweighs its increased aggregate state
under the declared policy/horizon. Its transition charges rebuild 80, ten renumberings, four Binding
publications and overlap 147. The dense split is rejected; its tiny controller reduction cannot justify
nearly doubling aggregate state. A merge from that forced correctness-control layout back to flat is
accepted and actually executed as local generation 2. External hard updates remain zero by design:
preserving the Scope's parent contract is containment, not a claim that exported state shrank.

All fourteen requested criteria pass. Exhaustive ordered-pair correctness is checked only on these tiny
layouts. The dense graph explicitly takes `0 -> 3 -> 1`, leaving and re-entering child `{0,1,2}` rather
than forcing its expensive interior link. Owning STPs stay internal, but end-to-end routes are not tree
paths. Disjoint Scope regions independently advance generations; no global configuration epoch is used.

## Reproduce / limits

```bash
uv run --locked python src/scope_evolution_main.py
uv run --locked python scripts/check.py
```

Output schema: `netsynth.scope-evolution.semantic-probe.v1`. Graphs, hand-selected generation parameters,
policy weights, budget components, structural cost and validation results are machine-readable.
Frozen Scale-4/5/6 and Security Floor source remains unchanged.

No hidden global topology dependence or Scope-as-path-tree rule was found. The specified local structural
semantics appear coherent enough to freeze; the prototype does not validate a production rollout protocol.
Remaining choices include durable prefix/generation allocation after controller restart, drain/expiry
policy, asynchronous activation/failure recovery, measured long-lived benefit estimators, deployment
budget profiles and exact wire encoding. Multi-level reparenting is not simulated; this prototype handles
one stable enclosing Scope's child split/merge and exposes its unchanged BTG for existing parent composition.

Per-layout two-level ownership and tiny full boundary matrices are validation choices, not mandatory
fanout/depth, separator algorithms or a generic graph-partition framework. Soft export metrics are fixed
placeholders; no path-quality/stretch claim is made. Query state is retained until explicit retirement in
the tiny workload; routine query expiry/reclamation remains an implementation policy. Hard external
contract changes use the already frozen Scale-4 generation rules, not hidden resurrection in this adapter.
