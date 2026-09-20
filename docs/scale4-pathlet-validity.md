# Scale 4 Pathlet Validity and Update Semantics

> Status: architecture choice.
>
> This document answers:
>
> How do Scoped Transit Pathlets and cached Route Programs remain safe under asynchronous topology changes without a globally synchronized routing epoch?

## 1. Design goal

NetSynth prefers:

- local repair first;
- no globally synchronized update transaction;
- no requirement that every ingress immediately hear every withdrawal;
- stale state may fail, but must not silently change meaning.

The architecture therefore prioritizes **safety of stale references** over guaranteed uninterrupted delivery during arbitrary change.

## 2. Prior-art reconciliation

SCION combines cached packet-carried paths with expiration, revocation, and on-demand refetch. MPLS experience explicitly warns that withdrawn labels must not be reused while stale packets can still exist. Consistent-update work shows that global/per-packet version tags can provide stronger atomic transition semantics, but with coordinated installation.

NetSynth does not choose global configuration epochs as the common Scale-4 mechanism. Reusable Scope-local pathlet objects need a narrower guarantee.

## 3. Architecture choice: immutable pathlet generation

A published Scoped Transit Pathlet is an immutable contract generation.

Conceptually:

    PathletHandle = { scope-local slot/FID, generation }

and the referenced object fixes:

- ingress boundary;
- egress boundary;
- owner Scope;
- generation.

The internal physical realization may change while the generation remains active, but its externally visible contract may not.

## 4. Hidden local repair

If an internal topology change occurs and the owner Scope can still realize the same ingress-to-egress transit service, the same generation remains valid.

No hard-contract parent update is required and no cached Route Program is invalidated. A soft route metric may change and may be refreshed separately.

## 5. Contract-breaking change

If the owner can no longer realize the generation's ingress-to-egress transit semantics:

1. that generation becomes invalid for new forwarding;
2. the owner disables its local forwarding realization;
3. the parent-visible BTG withdraws it;
4. a replacement may be published as a **new generation**.

Packets or cached Route Programs referencing the old generation may fail. They must never be reinterpreted as the replacement generation.

## 6. Fail-closed stale reference

When a router receives a Transit Label whose pathlet generation is no longer active:

    unknown/retired generation -> transit failure

not:

    reinterpret label / fallback / guess another pathlet

Hop Budget still bounds other inconsistent forwarding behavior.

## 7. Generation-safe label reuse

A compact local FID/slot may eventually be reused, but stale references must remain distinguishable. Conceptually the packet-visible transit handle includes a generation discriminator.

Equivalent implementations may encode slot+generation, allocate a fresh opaque handle, or quarantine retired labels with an epoch mechanism. The architecture requirement is semantic: a stale pathlet reference can never alias a newer unrelated pathlet.

Exact bit width is deferred.

## 8. Make-before-break when possible

For planned change or metric optimization, the owner should prefer:

1. install new internal realization;
2. publish a new pathlet generation;
3. allow Route Compilers to begin using it;
4. keep the old generation valid during overlap;
5. retire the old generation later.

The parent may temporarily advertise both generations.

Unexpected hard failures may make overlap impossible; stale programs then fail closed.

## 9. Soft Route-Program cache

A cached Route Program is soft state. It records at least the pathlet generations it references and a refresh policy.

The architecture does not require perfect reliable push invalidation to every cache. Known withdrawals invalidate matching cache entries immediately; stale programs are periodically refreshed; failure observed at the edge triggers route recompilation/retry.

Precise retry/error signaling is deferred until transport/control feedback is derived.

## 10. No global-clock correctness requirement

Time-based refresh or advertised lifetime may improve cache behavior, but forwarding safety does not depend on globally synchronized clocks.

Safety comes from generation-safe handles and fail-closed lookup. Lifetime therefore improves liveness/performance rather than being the only protection against stale aliasing.

## 11. Parent BTG update semantics

A parent's BTG view is a set of currently advertised immutable pathlet generations.

Updates are object-local:

    ADD generation
    WITHDRAW generation

A parent need not replace the entire child summary atomically. Different Route Services may temporarily know different active sets.

A route compiled from an already-withdrawn object may fail, but cannot silently route under a different generation.

## 12. Route Program dependency semantics

A Route Program is valid only through the pathlet generations it references.

Internal realization changes that preserve those generations are invisible.

This yields three change scopes:

- internal repair: no Route Program dependency changes;
- pathlet-generation replacement: only programs using that generation become stale;
- structural Scope/Locator change: potentially many programs change and is a slower architectural event.

## 13. Revocation is an optimization, not a safety prerequisite

An implementation may disseminate withdrawal/revocation information to parent Route Services, recently querying caches, or higher-level route caches.

SCION demonstrates the usefulness of revocation caches and on-demand refetch.

But correctness must not depend on every caching ingress hearing a withdrawal before its next send.

## 14. Why no global configuration version

A global per-packet configuration version is appropriate when every rule update must appear atomic network-wide.

NetSynth weakens that requirement: each reusable path service is independently versioned and Scope-owned. A packet may traverse pathlets from different publication times as long as every referenced generation is individually valid and composable at its boundaries.

This avoids turning one local repair into a global update barrier.

## 15. Structural changes are separate

This mechanism handles physical link/node changes, internal pathlet rerouting, and BTG pathlet add/withdraw.

It does not yet define Scope split/merge, Locator renumbering, Endpoint movement, or stable identity.

## 16. Minimal validation eventually required

Validate only NetSynth-specific semantics:

1. hidden repair preserves old Route Programs;
2. contract-breaking failure invalidates only dependent programs;
3. stale handles fail rather than alias;
4. make-before-break allows old/new generations to coexist;
5. asynchronous parent knowledge cannot cause semantic misinterpretation;
6. no global epoch is needed for safety;
7. withdrawal/update propagation remains scoped to owners/consumers rather than all forwarding nodes.

Do not re-prove generic consistent-update or lease theory.

## 17. Scale-4 state after this choice

    Structured Locator
            |
    Scoped Route Resolution
            |
    Route Program
            |
    versioned Scoped Transit Pathlets
            |
    Transit Stack / label switching
            |
    physical forwarding

Control state is organized by laminar Routing Scopes:

    internal topology/detail
        -> stable BTG/STP contracts
        -> parent Scope

Destination-specific routes are pulled and cached rather than globally flooded.

## 18. Next architecture question

The basic Scale-4 routing mechanism is now coherent enough that the next step should not add another routing feature.

The next step is to audit Scale 4 as a whole:

- what state exists at each lifetime;
- what information is global, Scope-local, ingress-local, and packet-local;
- where theory gives hard bounds;
- whether any mechanism is redundant;
- whether the design gracefully collapses back to Scale 0-3;
- whether this architecture has simply reinvented Pathlet Routing / SCION / H-PCE under different names.

Only after that audit should NetSynth either freeze Scale 4 or revise it.