# Scope Formation and Restructuring Policy

> Status: architecture choice.
>
> Question:
>
> What property should determine Routing Scope boundaries, and when should the hierarchy be restructured?

## 1. Scope is not a route-geometry tree

The frozen architecture already establishes:

~~~text
Scope hierarchy = knowledge / ownership / change-containment structure
physical routes  = arbitrary graph routes
~~~

Therefore Scope formation must not optimize only:
- shortest-path stretch;
- prefix-monotone path shape;
- tree embedding quality.

Those were earlier project mistakes.

## 2. Theory reconciliation

Graph partitioning, separators, sparse partitions/covers, spanners and hierarchical decompositions provide mature tools for finding regions with useful locality and small interfaces.

They also show that:
- good decompositions depend on graph family;
- some graphs have no small balanced separators;
- no hierarchy can universally compress every arbitrary graph while preserving all desirable routing properties.

Dynamic graph-partitioning work further makes the migration trade-off explicit: reorganizing partitions may reduce future cross-boundary cost but itself has a movement/reconfiguration cost.

NetSynth does not invent a new universal partition algorithm.

## 3. Architecture choice: control-budgeted connected Scopes

A normal Routing Scope should be a **connected physical/control region**.

Connectivity is chosen because an STP owned by a Scope must be realizable without leaving that Scope. A disconnected ownership region provides no useful common internal transit substrate and makes local failure/change containment ambiguous.

Each Scope is formed to keep three kinds of control cost manageable:

### Local control cost

The detailed state/computation required inside the Scope.

Examples:
- local topology/routing state;
- child BTGs;
- Route-Service query work;
- pathlet realization state.

### External contract cost

The state exported to the parent.

Examples:
- number/size of boundary interfaces;
- BTG/STP summary size;
- parent-visible routing metadata.

### Export churn

How often internal events force a **hard parent-visible contract change** rather than being repaired locally.

A good Scope hides many internal changes behind a relatively small and stable external contract.

## 4. Boundary quality principle

Informally, a strong Scope boundary has:

~~~text
large / active interior
        |
        | hidden by
        v
small, stable boundary contract
~~~

A poor Scope boundary has:

~~~text
small interior
but
large / rapidly changing external contract
~~~

The architecture therefore values:

> internal complexity divided by externally visible complexity/change.

No universal scalar objective is frozen.

## 5. Scope budgets

An implementation/deployment may define soft budgets such as:

~~~text
max local control state
max Route-Service work
target maximum boundary-summary size
target maximum exported hard-update rate
target hierarchy depth
~~~

These are **control budgets**, not packet semantics.

They may depend on machine capability and deployment profile.

A Scope should be considered for restructuring when it persistently exceeds its control budget.

## 6. Split

A Scope may split its internal child layout when:

- local control state/computation is persistently too large; or
- one internal region has strong locality and can be summarized behind a substantially smaller/stabler boundary; or
- exported churn can be reduced by isolating a volatile region.

A split should prefer connected children whose cross-child interfaces are small/stable relative to their interiors.

Separator / graph-partitioning / clustering algorithms are implementation tools for finding such candidates.

## 7. Merge

Sibling Scopes may merge when:

- their boundary contract between each other is almost as complex as their combined internal topology;
- maintaining separate Route Services provides little containment benefit;
- one or both Scopes are persistently far below local-control budgets;
- repeated structural changes show that the boundary is unstable.

This prevents hierarchy from surviving merely because it already exists.

## 8. Do not chase fast traffic demand

Application traffic demand can change much faster than Scope structure.

NetSynth therefore does not restructure Scope ownership in response to short-lived traffic hotspots alone.

Traffic/query statistics may be a slow advisory signal, but Scope layout primarily follows:
- topology/control complexity;
- failure/change locality;
- boundary stability.

Fast load balancing belongs in routing/path selection, not hierarchy restructuring.

## 9. Restructure hysteresis

Structural change is expensive:

- new layout construction;
- Locator renumbering;
- Endpoint Binding updates;
- old/new overlap;
- control-state rebuild.

Therefore a temporary improvement is insufficient.

A restructure should require a persistent expected benefit that exceeds migration/churn cost by policy-defined hysteresis.

Conceptually:

~~~text
expected long-lived control benefit
        >
structural transition cost + safety margin
~~~

The exact estimator is not frozen.

## 10. No mandatory fixed fanout or depth

NetSynth does not define:

~~~text
every Scope has k children
hierarchy depth = log_k(N)
Scope size = constant
~~~

The hierarchy is driven by control compressibility.

Tree-like / modular topologies may form deeper effective hierarchies.

Poorly separable topologies may remain shallow and comparatively flat.

## 11. Noncompressible-region rule

If every reasonable partition of a region produces:
- large boundary state;
- high cross-boundary churn;
- little reduction in parent/local control work;

then **do not manufacture hierarchy**.

Keep the region flatter and pay the honest state cost.

This is the operational consequence of separator/compact-routing lower-bound intuition.

Hierarchy is optional compression, not a correctness requirement.

## 12. Parent-visible stability dominates internal elegance

When comparing two layouts with similar local state, prefer the one whose parent-visible hard contract changes less often.

Reason:

~~~text
internal change
    -> local work

exported hard change
    -> invalidates parent state
    -> may propagate upward
    -> may invalidate cached Route Programs
~~~

Thus change containment is a first-class optimization target.

## 13. Scope boundaries are not administrative boundaries

An operator may constrain Scope placement for physical/organizational reasons, but NetSynth does not equate:

~~~text
Scope = AS
Scope = organization
Scope = subnet
Scope = security zone
~~~

A Scope is a routing-control ownership/compression object.

Administrative policy may constrain candidate partitions without redefining the architecture.

## 14. Failure-domain hints

Shared failure domains may be useful formation hints.

For example, isolating a highly correlated failure region can reduce how far its repeated changes propagate.

But failure domains are not required to align exactly with Scope boundaries, and failure-domain labels are not packet-visible routing semantics.

## 15. Layout algorithm boundary

The architecture freezes:
- connected laminar ownership;
- control-budget motivation;
- external-contract/churn criteria;
- hysteretic restructuring;
- honest flat fallback.

It does **not** freeze:
- METIS-like partitioning;
- separator algorithms;
- spectral clustering;
- sparse-cover construction;
- learned partitioning;
- one global objective function.

Those may be compared as control-plane implementations.

## 16. Structural-change locality

When a Scope changes only its child layout, the transition machinery from `structural-scope-evolution.md` applies.

If the Scope preserves its own parent-visible STP contracts, the restructure stops there.

Thus the architecture aims for:

~~~text
layout optimization local to S
        +
no parent-visible hard change
        =
no higher-level restructure/update
~~~

## 17. Root / top-level reality

The architecture does not claim the root/global region is always strongly compressible.

If global topology is poorly separable, upper-level BTGs/control state can remain large.

This is an explicit limitation rather than a reason to create fake hierarchy.

Replication/distribution of a high-level Route Service may address computational availability, but does not make information-theoretic state disappear.

## 18. What must be validated

The NetSynth-specific question is not whether a graph partitioner can find separators.

Minimal validation should test only architecture behavior under two deliberately different layouts:

1. a modular topology where a good Scope split strongly reduces exported state/churn;
2. a poorly separable topology where forcing hierarchy provides little benefit.

The validation should demonstrate:
- budget metrics can be computed from existing architecture objects;
- split/merge candidate evaluation charges boundary state and structural migration cost;
- hysteresis prevents layout thrash;
- a noncompressible region is allowed to remain flat;
- route correctness does not depend on the chosen partition.

Do not search for an optimal partition or rediscover separator theory.

## 19. Architecture state

At this point Scope hierarchy has a complete lifecycle:

~~~text
formation:
    connected control-budgeted regions

steady state:
    child BTG / STP summaries

ordinary change:
    local repair behind stable contracts

structural pressure:
    evaluate split / merge

transition:
    versioned old/new layouts, make-before-break

retirement:
    old Locators/layout generation removed
~~~

## 20. Next step

Scope formation and structural transition semantics are now sufficiently specified for a **minimal structural-control validation**.

No new routing abstraction should be added before that validation.
