# Scale 4 Re-derivation: Large-Scale Routing

> Status: architecture design, not an implementation specification.
>
> Research order used here: architecture question -> theory reconciliation -> architecture choice -> minimal validation.

## 1. Starting point

Scale 3 already has:

- an arbitrary physical forwarding graph;
- hop-by-hop target-based forwarding;
- a routing/control function distinct from packet forwarding;
- local reaction to link/node change where possible;
- a finite Hop Budget for transient inconsistent forwarding state.

For a small/medium graph, full topology knowledge and flat per-destination forwarding state are still acceptable.

Scale 4 asks only:

> What must change when the forwarding graph becomes globally large?

## 2. What breaks first

A naive Scale-3 implementation has at least three scaling failures.

### Per-node persistent state

Full topology and/or one next-hop entry per global destination grows with total network size.

### Control construction cost

Computing and distributing globally detailed routing state becomes increasingly expensive even if packets remain simple.

### Change propagation radius

A local topology event can become a network-wide routing event.

This conflicts directly with the NetSynth principle:

> faster-changing information should have smaller propagation scope.

## 3. Theory reconciliation

Existing routing theory already rules out a free solution.

Compact-routing results show that on arbitrary weighted graphs one cannot universally combine:

- sublinear local routing state;
- arbitrary topology-independent names;
- stretch arbitrarily close to one;
- no additional label/header/setup information.

Name-dependent compact-routing schemes achieve strong state/stretch trade-offs by assigning topology-sensitive labels. Name-independent schemes prove that stable arbitrary names are possible, but pay elsewhere in local state, packet/header information, distributed lookup machinery, or stretch.

Hierarchical routing, sparse covers, spanners, emulators and metric embeddings likewise show that route-state compression necessarily trades against path quality and/or representation complexity on hostile graph families.

Therefore NetSynth must choose where to place unavoidable routing information.

## 4. Architecture choice A: use a topology-dependent forwarding Locator

At Scale 4, NetSynth chooses a network-assigned **Locator** for forwarding participants.

This is an explicit architecture preference, not a theorem-imposed necessity.

Reasons:

1. the hot path should not perform a distributed stable-name lookup merely to make one forwarding decision;
2. topology-dependent destination information lets the routing system exploit known compact-routing techniques;
3. the common forwarding plane should remain semantically poor;
4. stable application identity is a different lifetime problem and can be introduced only when Scale 5 forces it.

The Locator is not yet an Endpoint ID.

A later stable identity mechanism may resolve to one or more current Locators, but Scale 4 does not require that mechanism yet.

## 5. Architecture choice B: retain Routing Scope, but only as control/compression structure

NetSynth retains a **Routing Scope** abstraction.

A Scope is a slow-changing topology/control ownership region used to:

- bound detailed knowledge;
- aggregate routing information;
- contain change propagation;
- give topology-dependent structure to Locators.

A Scope is **not** a routing tree and does **not** constrain physical paths.

This explicitly rejects the later Phase-3/4 prefix-monotone interpretation.

A valid route may:

- cross sibling scopes;
- leave a scope containing the destination;
- re-enter it later;
- use any physical cross-link justified by the available routing information.

The hierarchy structures knowledge, not legal path geometry.

## 6. Why Scope membership is laminar

NetSynth deliberately chooses a laminar architectural Scope hierarchy:

- every forwarding participant has one ownership lineage;
- every routing/control object has an unambiguous enclosing domain;
- update propagation has a clear upward boundary;
- Locator components have one interpretation at each resolution;
- restructuring can be reasoned about as old/new lineage overlap.

This is an operational simplicity choice, not a claim of mathematical optimality.

Overlapping sparse covers, landmarks, tree covers, spanners and other mathematical structures may be used **inside** a Scope's routing algorithm or summary construction. They are not themselves promoted to architectural Scope membership.

## 7. Structured Locator returns as a candidate architecture choice

With laminar Scopes, the Scale-4 forwarding Locator is again naturally structured:

~~~text
<s1, s2, ..., sk, local>
~~~

where each component is meaningful only within its parent Scope.

Its semantics are deliberately limited:

- it identifies the destination's topology/control lineage;
- it lets distant nodes reason at coarse resolution;
- it is not a source route;
- it does not require prefix-monotone forwarding;
- it may change when slow Scope structure changes.

Exact wire encoding and bit allocation remain undecided.

## 8. Architecture choice C: exact global shortest paths are not a common-core promise

Scale 4 explicitly accepts approximate routing.

The common architecture promises neither:

- globally shortest paths;
- a fixed universal stretch bound independent of the chosen mathematical construction.

Instead, it requires that path-quality loss be explicit and measurable.

The mathematical routing construction chosen later should provide a known bound where possible.

This choice is necessary to avoid restoring flat global state under another name.

## 9. Architecture choice D: exported state is the change-propagation boundary

Each Scope maintains detailed information internally as required by its local routing construction.

To its parent it exports a bounded **Routing Summary Contract**.

A local event:

1. updates detailed state inside the smallest affected Scope;
2. is absorbed there if the exported contract remains valid;
3. propagates upward only if that contract changes.

This is the main operational reason Scope exists.

The architecture does not yet define the exact summary representation.

## 10. Knowledge boundary

A parent may use only:

- its own local/child-level state;
- child Routing Summary Contracts;
- physical links crossing between its immediate children.

It may not query arbitrary descendant topology or invoke hidden descendant shortest-path planners.

This boundary survives the Phase-2/3 oracle-leak lessons.

## 11. Packet format remains minimal for now

Do **not** add a generic mutable routing header merely because compact-routing theory permits one.

At this point the candidate transit unit remains conceptually:

~~~text
Destination Locator
Hop Budget
Payload
~~~

The next architecture problem may prove that physically realizing compressed/virtual routing information requires a small mutable routing context.

If so, that field should be introduced because the architecture problem forces it, not because a general simulator interface supports it.

## 12. Non-compressible regions

The architecture does not assume every graph region compresses well.

If a Scope's external routing contract approaches the complexity of its interior:

- do not claim compression;
- stop adding artificial hierarchy merely to preserve the model;
- accept a larger local state/stretch trade-off, or use a known compact-routing construction internally.

This is an honest degradation mode consistent with lower bounds on hostile graphs.

The common architecture still remains Scope-based because Scope's primary role is ownership/change containment, not a theorem that every Scope saves state.

## 13. What earlier experiments remain relevant

Phase 1-5 remain useful for:

- demonstrating hidden-oracle hazards;
- measuring Scope ownership/churn semantics;
- exploring summary composability;
- showing why prefix-monotone forwarding should not be an architectural rule.

They no longer establish the mathematics of compact routing or decomposition.

## 14. Next architecture question

The next question is now precise:

> What exactly must a child Scope export to its parent so that the parent can make useful large-scale routing decisions, while the representation remains sparse, path-realizable, and locally maintainable?

This is the **Routing Summary Contract** problem.

Before designing it, reconcile with:

- terminal/subsetwise spanners;
- path-reporting distance oracles;
- emulators;
- distance preservers;
- compact routing;
- sparse covers.

The architecture must then choose one concrete semantic contract.

Do not implement anything before that choice.
