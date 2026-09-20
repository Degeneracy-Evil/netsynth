# Research Method: Theory Reconciliation Gate

> This gate is mandatory before proposing a new NetSynth phase, routing mechanism, summary representation, decomposition algorithm, or large experiment matrix.

## Step 1 — Mathematical reduction

State the current architecture problem in protocol-neutral mathematical language.

Examples:

- routing table state vs path stretch;
- terminal metric compression;
- pairwise distance preservation;
- graph decomposition with bounded overlap/diameter;
- distributed shortest-path convergence;
- fault-tolerant reachability;
- name-dependent routing labels.

Do not design a new mechanism yet.

## Step 2 — Literature map

Search classic, survey, and current literature.

At minimum record:

- closest standard problem names;
- strongest applicable upper bounds;
- known lower/impossibility bounds;
- approximation or hardness results;
- special results for relevant graph families;
- known distributed/dynamic constructions if NetSynth cares about control-plane realization.

Prefer original papers or authoritative surveys.

## Step 3 — Applicability table

For every candidate theorem/construction, compare its model to NetSynth on:

```text
graph type / weights
name-dependent vs name-independent
state measure
header/label measure
stretch definition
centralized vs distributed construction
static vs dynamic
fault model
virtual edges allowed?
physical realization required?
state ownership/replication
recursive composability
```

Mark each item:

- directly applicable;
- applicable after translation;
- not applicable because of a specific model difference.

## Step 4 — Adopt, do not reinvent

If an existing theorem or construction answers the mathematical core, use it as a baseline or building block.

Do not create a home-grown weaker substitute merely because it is easier to simulate.

If exact implementation is too large initially, implement a small faithful reference and preserve the theoretical guarantee in the design document.

## Step 5 — Define the NetSynth delta

A new phase is justified only by a residual question such as:

- ownership/locality not modeled in theory;
- recursive summary composition;
- physical realization of emulator edges;
- bounded packet context;
- update/churn locality;
- identity-to-locator split;
- profile-specific constants;
- interaction between several known primitives.

Write this delta explicitly before experiments.

## Step 6 — Minimal experiment

Design the smallest experiment that can falsify the NetSynth-specific claim.

Do not run broad topology/parameter sweeps to rediscover a theorem.

Every experiment should say which result it is **not** trying to rediscover.

## Step 7 — Exit criterion

A phase exits when the architecture-specific question is answered.

Do not turn a theorem-backed conclusion into another simulation phase just for additional confidence.

## Required phase-document header

Every future phase document must begin with:

```text
Mathematical abstraction:
Closest established problems:
Known upper bounds:
Known lower bounds / impossibility:
Known constructions:
Why these results do not fully answer NetSynth:
NetSynth-specific question:
Minimal experiment required:
```

No implementation prompt should be issued before these fields are substantively filled.
