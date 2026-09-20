# NetSynth Architecture Re-centering

> Status: current project-direction note.
>
> NetSynth is a clean-slate network-architecture project, not a general routing-algorithm framework. Established mathematics is a constraint and a tool; it does not replace architecture choice.

## 1. Research order

The required order is:

~~~text
architecture question
    -> theory reconciliation
    -> explicit architecture choice
    -> minimal validation
~~~

Not:

~~~text
literature survey
    -> expose every known alternative as a first-class architecture abstraction
    -> build a universal plug-in framework
~~~

A simulator may support many baselines. NetSynth itself eventually must choose one coherent architecture.

## 2. Three layers that must not be confused

### NetSynth architecture

The actual answer to:

> If compatibility were irrelevant, how should a modern computer network be designed?

Architecture defines the common packet/forwarding/control/naming abstractions and their lifetimes. It must make concrete choices.

### Research/theory layer

Used to:
- identify known lower/upper bounds;
- reject impossible ideas early;
- adopt mature constructions where appropriate;
- understand graph-family limits;
- provide comparison baselines.

Compact routing, spanners, emulators, metric embeddings, separator theory, labeling schemes, DUAL, etc. belong here unless NetSynth explicitly chooses one as part of its architecture.

### Simulator/research infrastructure

May be more general than the architecture so that alternatives and baselines can be compared.

A generic RoutingScheme interface, resource accounting, topology generators, TCP/IP baselines, compact-routing baselines, legacy Scope routing, etc. can exist here without becoming NetSynth architectural abstractions.

Simulator generality must never imply architecture agnosticism.

## 3. Reclassification of recent theory-driven ideas

### Keep as research method

- theory reconciliation gate;
- theory baseline registry;
- explicit theorem/implementation/measurement separation;
- theory-compatible resource accounting;
- distinction among spanner / emulator / oracle / routing scheme / cover.

These improve research quality but are not network protocol concepts.

### Keep as simulator infrastructure candidates

- a generic routing-scheme adapter;
- bit/header/table/session resource accounting;
- EndpointSet / AttachmentRelation as a neutral scenario model;
- baseline support for name-dependent and name-independent schemes;
- generic port-model metadata.

These may help experimentation. NetSynth packets and routers do not need to expose these abstractions.

### Keep only as open architecture questions

- Structured Locator versus arbitrary routing label;
- stable Endpoint ID versus direct name-independent routing;
- explicit Rendezvous versus in-path lookup;
- writable routing header versus fixed destination-only header;
- Channel/session routing context;
- laminar Scope hierarchy versus overlapping/multi-structure routing state.

Theory has shown these are design choices, not necessities. They must be re-derived from architecture goals.

### Historical candidate, not current universal architecture

The Phase-1 to Phase-5 family:

~~~text
ScopeTree
Structured Locator
prefix forwarding
scoped potentials
attachment lookahead
metric-aware decomposition
~~~

remains an important candidate and experiment history. It is not discarded, but it is no longer assumed to be NetSynth's final routing architecture.

## 4. What still survives from the first-principles derivation

The strongest architecture conclusions remain the early ones.

### Scale 0

A direct point-to-point link needs:
- finite transfer boundaries;
- finite buffering;
- local rate/flow control.

No global addressing is intrinsically necessary.

### Scale 1

Branching creates:
- forwarding choice;
- contention and scheduling.

Addressing/routing information appears because a forwarding decision exists, not because packets intrinsically require IP-like addresses.

### Scale 2

A mesh creates:
- path choice;
- multipath;
- possible cyclic resource dependence.

The current architecture preference remains a simple hop-by-hop forwarding core rather than mandatory source routing, but the exact destination/header representation is reopened by theory reconciliation.

### Scale 3

Dynamics create:
- a routing/control function distinct from per-packet forwarding;
- inconsistent transient state;
- a need to bound pathological forwarding, for which Hop Budget remains a strong candidate;
- a strong preference for absorbing changes locally before propagating them widely.

These remain architecture-level conclusions because they arise from the physical/operational problem itself rather than one compact-routing construction.

## 5. Where the architecture should resume: Scale 4

The project should resume from the first unresolved large-scale architecture question:

> When the forwarding graph becomes very large, how should destination information and routing knowledge be represented so that per-node state and change propagation remain bounded, without making the data plane complex or forcing globally bad paths?

Known theory immediately constrains the answer:
- universal compact routing has unavoidable state/stretch trade-offs;
- name-dependent and name-independent models place information differently;
- graph families differ fundamentally;
- hierarchical/tree-like representations can incur distortion;
- mutable headers and handshakes are legitimate resource dimensions.

But theory does not choose NetSynth's architecture for us.

## 6. Architecture criteria for the Scale-4 choice

The next routing architecture choice should be judged against explicit NetSynth values:

1. **Thin hot path** — per-hop forwarding should remain simple enough for hardware implementation.
2. **Bounded persistent state** — global scale must not require every node to store every destination.
3. **Locality of change** — local topology/attachment changes should avoid global churn when possible.
4. **Graceful degeneration** — tiny networks should not need large-scale machinery.
5. **Explicit information placement** — state in routers, packets, labels, directories, or sessions must be visible, not hidden.
6. **Reasonable path quality** — not necessarily exact shortest path.
7. **Arbitrary physical graph** — the architecture must not claim the physical network is a tree.
8. **Operational clarity** — virtual/theoretical structures must have a real hop-by-hop realization.
9. **Profile adaptability without flag soup** — specialized profiles may optimize implementation, while the common architecture remains coherent.
10. **Slow-changing global structure, fast-changing local structure** remains a preferred design principle unless theory/validation disproves it.

These criteria, not simulator generality, decide among theoretical constructions.

## 7. What not to do next

Do not:
- implement the proposed universal R1 routing framework yet;
- add every compact-routing scheme as a first-class NetSynth abstraction;
- rename all architecture objects into maximally generic terms merely because theory has multiple models;
- resume Phase 6;
- rewrite the repository around plug-in routing schemes before the Scale-4 architecture choice is made.

A small simulator adapter layer may be useful later, but architecture comes first.

## 8. Next research task

Return to Scale 4.

The next work should answer:

1. What exact large-scale failure of the Scale-3 architecture forces a new abstraction?
2. Which known mathematical models describe that failure?
3. Which resource trade-offs are unavoidable?
4. Given NetSynth's architecture criteria, which information-placement strategy do we actually prefer?
5. What is the smallest architecture commitment necessary at Scale 4?
6. What minimal validation distinguishes that choice from the strongest alternatives?

Only after this choice stabilizes should code architecture be reconsidered.
