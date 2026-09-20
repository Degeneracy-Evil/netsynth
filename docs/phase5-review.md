# Phase 5 Architecture Review

> Reviewed implementation: `915f4518146350c64c89da65a61215aa17c05499`.
>
> Result: Phase 5 validates Scope metric distortion as the correct predictor for prefix-monotone hierarchy stretch, but also exposes a hard compression frontier. Metric-aware decomposition can buy isometry by making the hierarchy deeper/finer and paying much more state; on random/expander-like graphs this can exceed Flat by a large margin.

## 1. What Phase 5 established

The D1 research oracle is architecturally honest:

- it is explicitly centralized;
- it reads global weighted distances only during Scope formation;
- that construction work is counted separately from forwarding state;
- forwarding semantics remain unchanged.

Its results support the Phase-4 isometry criterion. Lower Scope distortion strongly tracks lower full-lookahead hierarchy stretch.

The small-graph result where D1 drives average full hierarchy stretch from about 1.137 to 1.000 is therefore meaningful.

## 2. Why D1 is not a final answer

D1 often repairs distortion by selecting a deeper/finer hierarchy.

That increases:

- Locator depth;
- the number of Scope-local destination keys;
- full-lookahead attachment state;
- potential state;
- boundary-related state.

Thus D1 can recover shortest paths by gradually giving up the compression benefit that motivated hierarchy in the first place.

The 128-node expander-like result is the clearest warning: hierarchy stretch improves, but full state becomes far larger than Flat.

This is not an implementation failure. It is evidence that some graph families may have no large regions that are simultaneously:

- low-boundary;
- low-distortion;
- shallow enough to keep hierarchy state small.

## 3. Compression frontier

A Scope should now be judged on at least two independent axes:

```text
boundary / state cost
metric distortion
```

Decomposition only moves along this frontier.

For tree-like and geometric graphs, the frontier can be favorable.

For random/expander-like graphs, reducing distortion can require so much boundary/depth/state that the hierarchy stops compressing.

This is a structural property worth preserving in later experiments; do not tune it away.

## 4. Do not replace prefix-monotone routing globally

Phase 5 does not justify abandoning prefix-monotone forwarding.

Trees and mesh-like topologies remain strong cases for it, and its correctness/progress invariants are unusually clean.

A better next hypothesis is:

> keep prefix-monotone forwarding as the default, but add sparse, explicit exceptions only where a Scope's induced metric is materially worse than the physical metric.

This preserves the simple common case and makes non-isometry pay explicit state.

## 5. External metric closure

Let `B(S)` be the boundary interfaces of Scope `S`.

Any global path between two nodes in `S` can be decomposed into:

- segments inside `S`;
- external segments that leave at one boundary interface and re-enter at another.

Therefore, if every relevant boundary pair is given a virtual edge whose weight equals the best external detour cost, the augmented Scope can reproduce the unrestricted physical metric.

This gives an exact but potentially expensive reference:

```text
internal graph
+
all external boundary shortcuts
```

The shortcut set can be quadratic in `|B(S)|`, so this is not automatically a compression win.

## 6. New quantity: metric-repair complexity

For tolerance `epsilon >= 0`, define conceptually:

```text
R_epsilon(S) =
minimum number of external boundary shortcuts
needed so augmented Scope distortion <= 1 + epsilon
```

Exact optimization is not required immediately.

A greedy approximation is enough for experiments.

This quantity asks a stronger question than raw boundary size:

> How many explicit exceptions are needed to make this Scope behave metrically like the full graph?

It should be favorable for compressible topologies and large for hostile ones.

## 7. Why an escape needs explicit forwarding context

A virtual shortcut is not a physical next hop.

Its realization information must live somewhere:

1. destination-/shortcut-specific network state;
2. packet-carried temporary routing context;
3. per-path established state.

Using the ordinary destination Locator alone is insufficient to represent a virtual boundary-to-boundary edge without either replicating route state along the detour or introducing hidden path knowledge.

For the next experiment, use one explicit temporary Scope-local transit context. This makes the architecture cost visible rather than hiding it.

## 8. Next step

Phase 6 should study sparse external shortcuts as **metric repair**, not unrestricted Scope escape.

The primary comparison should be:

```text
D0 + sparse metric repair
vs
D1 + no escape
vs
Flat
```

on the same physical graphs.

The question is whether a small number of explicit exceptions gives a better state/stretch/failure tradeoff than globally forcing the hierarchy toward isometry.
