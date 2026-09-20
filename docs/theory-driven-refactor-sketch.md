# Theory-Driven Refactor Sketch

> **PAUSED — DO NOT IMPLEMENT YET.** This sketch describes possible simulator infrastructure, not NetSynth architecture. After architecture re-centering, the project must return to Scale-4 architecture derivation before deciding whether or how much generic framework refactoring is useful. Read `docs/architecture-recentering.md` first.

> Status: planning only. Do not implement until the architecture/theory reconciliation is approved.

## Likely code boundary

### Keep largely intact

- `graph.py`
- `topology.py`
- `failures.py`

These represent the physical problem instance and events and are not tied strongly to the current routing hypothesis.

### Replace/generalize

#### Current `routing.py` / `forwarding.py`

Replace the Scope-specific top-level API with a generic routing deployment/executor capable of labels, writable headers, optional setup, and physical next-hop decisions.

#### Current `metrics.py`

Introduce theory-compatible resource accounting: bits/words/header/session/control state plus measured stretch and update costs.

#### Current `experiment.py` / `phase3.py` / `scaling.py`

Replace Phase-number-specific orchestration with generic:

```text
Scenario
RoutingScheme
ControlPlaneModel
ResourceCostModel
Experiment
```

#### Current `decomposition.py`

Retain algorithms but move them under a scheme/structure namespace. Decomposition is not globally mandatory.

#### Current `summaries.py` / `attachments.py`

Retain as legacy Scope-routing construction modules; do not make new schemes express themselves as summaries.

### Add later

Potential package structure:

```text
netsynth/
    physical/
        graph.py
        topology.py
        failures.py

    routing/
        model.py          # generic labels/tables/headers/setup/step
        executor.py
        resources.py

        schemes/
            flat.py
            scope_legacy.py
            tree_labeling.py
            thorup_zwick.py
            ...

    metric/
        model.py
        spanner.py
        emulator.py
        covers.py

    control/
        model.py
        static.py
        distributed.py
        dynamic.py

    naming/
        endpoint.py
        resolution.py
        session.py

    experiments/
        scenario.py
        runner.py
        metrics.py
```

Names are provisional.

## Migration principle

Do not rewrite old Phase code in place.

First create the generic interfaces and wrap one or two existing schemes:

1. Flat exact routing;
2. current scoped-potential/attachment scheme as `scope_legacy`.

Once generic execution reproduces existing results, add theory baselines.

This avoids losing the historical experiments while removing them from the architecture center.

## First theory baselines after refactor

Tentative only:

1. exact compact tree routing / routing-label sanity baseline;
2. general weighted stretch-3 labeled compact routing baseline (Cowen / Thorup-Zwick family);
3. parameterized Thorup-Zwick handshake/session scheme;
4. name-independent compact routing baseline when Endpoint-ID-vs-label comparison starts;
5. selected sparse-cover/spanner/emulator baselines only when their semantic role is explicit.

Do not implement all at once.
