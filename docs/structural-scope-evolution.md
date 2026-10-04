# Structural Scope Evolution and Locator Renumbering

> Status: architecture choice.
>
> This document addresses a previously deferred problem:
>
> What happens when the forwarding substrate itself changes structurally — Scope split/merge/repartition/reparenting — so that Structured Locator lineage must change?

## 1. Why this is different from ordinary routing repair

Scale 4 already handles:
- link/node failure;
- internal pathlet rerouting;
- BTG pathlet add/withdraw.

Those events preserve the basic Scope ownership structure.

A structural event changes:
- immediate-child membership;
- boundary ownership;
- child labels / Locator lineage;
- possibly the shape of the Scope hierarchy itself.

This is intentionally a slower class of change.

## 2. Prior-art reconciliation

### Network renumbering

IPv6 renumbering work shows the practical importance of **make-before-break**:

~~~text
enable new prefix
    -> old and new coexist
    -> move usage to new
    -> retire old
~~~

A global flag day is unnecessary and operationally undesirable.

### Identifier / Locator split

ILNP and LISP illustrate why renumbering is much less disruptive once long-lived identity is separated from topology-dependent location.

NetSynth already has this separation:

~~~text
Endpoint ID
    !=
Structured Locator
~~~

Therefore changing Locator lineage does not change Endpoint identity or Channel identity.

### Consistent network updates

Per-packet versioned update mechanisms can provide strong global consistency across configuration transitions.

NetSynth does not require one global network configuration epoch for Scope restructuring.

Its frozen Route Programs, pathlet generations and fail-closed handles already provide explicit object-level versioning.

## 3. Architecture choice: stable Scope, versioned internal layout

A long-lived Routing Scope is an ownership/control object.

Its **internal child layout** may have generations.

Conceptually:

~~~text
Scope S

LayoutGeneration g1:
    child partition / labels / boundaries / child BTGs

LayoutGeneration g2:
    new child partition / labels / boundaries / child BTGs
~~~

A structural change preferably occurs inside the smallest enclosing Scope whose external role can remain stable.

## 4. Laminarity is per layout generation

For every active LayoutGeneration:

> each forwarding participant has one ownership lineage.

Thus each generation remains laminar.

During make-before-break migration, two layout generations may temporarily coexist inside the same stable enclosing Scope.

This transitional coexistence is **not** permission for arbitrary overlapping Scope membership in one architectural layout.

## 5. Locator generation

Structured Locator components are valid relative to the Scope-layout generation that assigned them.

Conceptually a locator path contains generation-qualified child labels:

~~~text
< child-label@g, child-label@g, ..., local attachment >
~~~

Exact encoding is not frozen.

The semantic requirement is only that old and new Locator lineages cannot be confused.

A stale old Locator must never silently resolve as a different new attachment after label reuse.

## 6. Make-before-break structural transition

For a planned repartition inside Scope S:

### Prepare

1. construct new LayoutGeneration g2;
2. allocate new child labels / Locator suffixes;
3. build new child routing state and BTGs;
4. ensure new paths/contracts are executable;
5. keep g1 fully operational.

### Activate

Affected attachment positions become reachable under new Locators.

An Endpoint may temporarily publish:

~~~text
EID -> { old Locator, new Locator }
~~~

Scale-5 Binding already supports this.

### Shift

New binding resolutions / Route Programs prefer the new Locator/layout according to policy.

Existing Channels may continue over the old Locator until path replacement is needed or policy migrates them.

### Retire

1. stop publishing old Locators for new use;
2. allow old Route Programs / STP references to drain or expire;
3. withdraw old layout routing objects;
4. retire g1.

No global simultaneous cutover is required.

## 7. Structural transition is local when possible

Suppose only the child partition inside Scope S changes.

If S can preserve the same parent-visible hard STP contracts, S's parent does not need to know that its internal layout changed.

Thus:

~~~text
child-layout restructure
        |
        v
can S preserve parent-visible STPs?
        |
      yes
        |
       STOP
~~~

This is the structural analogue of hidden pathlet repair.

If S's external BTG hard contract must change, normal pathlet-generation updates propagate upward only as needed.

## 8. Route Programs do not require a global layout epoch

A Route Program already references explicit:
- Locator information;
- pathlet handles/generations;
- local transit actions.

Therefore old and new Route Programs may coexist.

Each referenced object is independently valid or fails closed.

NetSynth does not add a packet field meaning:

~~~text
GLOBAL_NETWORK_CONFIGURATION_VERSION
~~~

merely for structural migration.

## 9. Infrastructure and direct-Locator traffic

Infrastructure objects addressed directly by Locator may temporarily advertise/support both old and new Locators.

Control services required to bootstrap a transition must remain reachable through at least one already-valid Locator until the replacement path is established.

This is the same make-before-break rule applied to infrastructure itself.

## 10. Break-before-make

Unexpected structural loss can prevent overlap.

Then stale behavior is already defined:

~~~text
old Locator / Route Program
    -> no longer valid
    -> fail closed

EID communication
    -> fresh Binding resolution
    -> new Locator when available
    -> new Route Program
~~~

Availability may be interrupted, but identity is not redefined.

## 11. Structural renumbering cost is explicit

Changing a Locator lineage may require Binding updates for every Endpoint attached beneath the changed region.

NetSynth explicitly accepts this cost for now.

Reason:
- structural Scope change is intended to be slow;
- EID/Channel continuity isolates applications from the renumbering;
- adding another permanent Locator-indirection layer only to avoid rare Binding churn would duplicate Scale-5 mapping machinery.

If future measurements show Scope restructuring frequent enough that this cost dominates, that is evidence to revisit the trade.

Do not pre-emptively add another stable attachment identifier.

## 12. Label reuse

Old child labels / Locator components may eventually be reused only when stale old Locators cannot alias the new meaning.

Implementation options include:
- generation-qualified labels;
- fresh opaque labels;
- bounded quarantine with an explicit reuse generation.

The architecture freezes only the anti-alias invariant.

## 13. Scope identity versus layout identity

A Scope may remain the same control/ownership object while its child layout changes.

A true Scope split/merge at the Scope's own parent level creates/retires Scope objects there.

The same local-generation transition mechanism applies one level higher.

Thus hierarchy restructuring composes recursively.

## 14. What this does not solve

This document does not decide:
- when a Scope should split/merge;
- what graph partition is best;
- maximum/minimum Scope size;
- boundary-count thresholds;
- automatic hierarchy optimization;
- administrative policy;
- how frequently restructuring is allowed.

Those belong to the next architecture question.

## 15. Minimal future validation

Before freezing structural evolution, a tiny semantic prototype should eventually demonstrate:

1. g1 and g2 layouts can coexist without violating laminarity inside either generation;
2. new Locator cannot alias old Locator semantics;
3. an Endpoint can temporarily publish old+new Locators without changing EID/Channel;
4. an existing old Route Program remains usable while g1 is active;
5. new traffic can compile through g2;
6. retiring g1 makes stale objects fail closed;
7. internal restructuring that preserves parent STPs causes no parent-visible hard update;
8. no global configuration epoch is needed.

Do not benchmark graph partitioning algorithms in this validation.

## 16. Next architecture question

Transition semantics are only half the problem.

The next question is:

> What property should determine Scope boundaries in the first place, and when is restructuring worth its churn cost?

That question must reconcile graph partitioning/separator theory with NetSynth's real architectural goal:

> Scope is primarily a knowledge/change-containment boundary, not a path-geometry tree.
