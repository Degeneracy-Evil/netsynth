# NetSynth v0.1: Expressiveness and Research-Value Equivalence Gate

Status: second adversarial derivation, 2026-10-10. Research assessment, not a change to frozen protocol semantics.

**Finding:** For the bounded, compiled, pre-installed, single-generation forwarding submodel investigated here, a strong hierarchical Pathlet + SR/BSID-style policy system can reproduce NetSynth's main control/data-plane behavior. A precise *real-world standard implementation equivalence* has **not** been proved. As a result, v0.1 has no established unique routing contribution and should not yet be a full-stack benchmark project.

## 1. Scope and prior-art audit

The strongest adjacent results are not a simple flat TCP/IP baseline:

1. Hierarchical area/pathlet control plane (Chiesa et al., 2014): internal topology local to an area, parent sees crossing pathlet between boundaries, arbitrary hierarchical levels.
2. Segment Routing BSID/SR Policy (RFC 8402, RFC 9256): opaque local policy behind a stable token, candidate-path changes without necessarily changing the externally referenced BSID; SR policy recursion and on-demand BSIDs are part of the RFC.
3. PNNI QoS topology aggregation and adaptive update policies (Chang & Hwang, 2002): updating external aggregates when cost changes exceed a threshold, balancing freshness against state distribution.
4. Segment-routing optimization with temporal reconfiguration budgets (Jaumard et al., submitted 2026-10-03): path traffic quality and configuration-change limits studied jointly. This result does *not* solve all state-placement questions, but rules out mere joint-objective novelty.
5. Compact-routing and optimal encoding literature: table/header/stretch trade-offs and path-encoding complexity.
6. HIP mobility, LISP ID/Locator mapping, SCTP reliable unordered messages, QUIC migration: substantial overlap with v0.1 endpoint and transport primitives.

This does not imply one deployed standard implements NetSynth end to end; it means the principal ideas and a strong combination are already available.

## 2. Model for a bounded expressiveness comparison

Consider a time interval where:
- the physical graph G is finite;
- a Scope layout generation is fixed;
- each chosen Route Program is a finite sequence of physical/crossing actions and valid STP invocations;
- each local compiled STP is finite and already installed;
- the code/context/forwarding-entry resources have explicit budgets;
- failures either preserve advertised hard STP contracts or cause fail-closed invalidation;
- no demand requires transit routers to maintain Channel/flow state;
- data-plane loops are bounded, and exact stale generations cannot alias replacements.

A NetSynth forwarding configuration is:

    X = (H, K, B, P, W, R)

where H is Scope ownership hierarchy; K is published boundary contracts; B is local reusable bindings; P is the ingress packet route program; W is bounded mutable packet context; R is the physical realization.

Compare against a **strong abstract baseline**, not a claim about unmodified deployed SR-MPLS hardware:

    Y = (areas/pathlets, local policies, BSID-like handles,
         finite packet segment program, bounded mutable context,
         pre-installed local tables)

Both systems have identical graph, hardware/action set, traffic, update observations, packet/context limits, and available local memory.

This definition matters: if the baseline were artificially forbidden from carrying a continuation token or installing a local macro, a NetSynth win would only reflect unequal permitted actions.

## 3. Constructive restricted simulation

We can map a static compiled NetSynth configuration into baseline Y.

| NetSynth item | Strong-baseline image |
| --- | --- |
| Routing Scope | Hierarchical area/control owner |
| BTG crossing summary | Advertised crossing pathlet / abstract border graph |
| STP | Area-local policy exposed as a pathlet |
| Public STP handle/generation | Locally scoped stable policy handle and exact version guard |
| Local BindingRef | Locally scoped BSID-like forwarding-label entry |
| PhysicalHop | Explicit adjacency forwarding action |
| Coarse packet Route Code | Finite segment/pathlet invocation program |
| Continuation Context | Pre-reserved label/continuation context |
| Spilled continuation | Pre-installed call-site-specialized local policy |
| Same-generation local repair | Change internal active local policy, preserve outer handle |
| Hard invalidation | Retire guard/handle and fail closed |
| EID/Locator | HIP/LISP-like identity/address separation outside routing |
| Channel | Message-oriented reliable secure transport, with SCTP/QUIC precedents |

Proof sketch (structural induction on the finite compiled instruction graph):

- **Base physical action:** a NetSynth local physical output action maps to the same baseline adjacency action; output link/path is unchanged.
- **Local token action:** map the owner-local token to a distinct owner-local forwarding entry with the same guarded action. Any lookup either produces the corresponding next state or the same fail-closed outcome.
- **Child invocation:** map the call into the child owner-local policy. Preserve the parent's continuation in the same pre-reserved context when possible, or in a pre-installed call-site-specialized entry when context is exhausted. The child policy's induction hypothesis matches the physical hops and eventual return.
- **Composition:** translate finite Route Code actions in order, keeping the packet/context budget and storing any common subprogram in reusable local state.
- **Internal repair:** substitute the new owner-local policy realization under the same external handle when hard conditions remain true. Only that owner's entries need change, as in the NetSynth model.
- **Withdrawal:** explicitly retire versioned local entries. Stale references fail closed in both abstract machines.

The argument shows *semantic reducibility in this deliberately capable abstract policy machine*. It does not establish:
- equality of concrete byte encodings;
- equal hardware cycles;
- support for all recursive/context actions in stock SR-MPLS/SRv6 ASICs;
- exact equality of control-plane wire protocols;
- correct asynchronous update ordering;
- full cross-domain trust/security equivalence;
- online optimality;
- a constant-factor translation cost for all possible dynamic programs without additional assumptions.

In particular, actual RFC 9256 SR Policy forwarding uses native SR-MPLS/SRv6 data planes; whether a stock datapath can emulate NetSynth's fixed, non-growing packet context and continuation semantics requires checking the supported actions and label-stack behavior. We **must not** silently grant deployed SR an instruction set that it lacks, nor deny it local macros it actually supports.

### Restricted conclusion

No *semantic impossibility* separates NetSynth from a sufficiently powerful hierarchical policy/BSID design in this compiled submodel.

This is not a full-theory equivalence theorem and not a proof that NetSynth can never outperform a specific implementation. It is sufficient to invalidate novelty claims based only on:
- opacity;
- same-handle hidden repair;
- packet/state placement;
- no per-flow transit state;
- bounded packet context;
- endpoint identity separation.

## 4. Performance and control-plane limits

### 4.1 No-information external routing counterexample

Choose two routes from boundary a to b:

Internal Scope S:
- state 0: cost 1;
- state 1: cost R squared;
- reachable in both.

External bypass E:
- cost R in both.

Let R > 1. Both states expose the identical reachability-only contract to the parent.

Any deterministic fixed outside decision must:
- pick S, causing state-1 stretch R, or
- pick E, causing state-0 stretch R.

Therefore worst-case stretch >= R. Arbitrarily large R means that binary stable reachability summaries **cannot ensure any universal finite constant stretch bound** while remaining observationally identical.

This is an elementary indistinguishability argument under deliberately limited observations, not a new theorem about every QoS summary.

NetSynth already permits soft metric updates. If it sends them, report **their full cost**, not only hard contract changes. The strong baseline may send the same updates.

### 4.2 Zero-update repair ties a strong baseline

A Scope has two internally edge-disjoint a-b routes.

NetSynth can rebind an STP without changing the outer code.

A baseline with area-local crossing pathlet and stable BSID can change the active candidate path without changing the outside token.

Thus on the metric "number of external hard-token updates" both score zero for this event.

A comparison against flat link-state flooding is not a fair novelty test.

### 4.3 Stable performance promises have a cost

Suppose the area advertises a delay/path-cost upper bound U. An internal failure leaves a backup costing L.

- If L <= U, the area can keep the advertised performance contract.
- If L > U, the area must withdraw/replace the guarantee, or breach it.
- If the summary advertises only reachability, it can hide the repair but cannot necessarily preserve good external routing decisions.
- If it advertises updated soft cost, external routing can improve but control changes are visible and counted.

The nontrivial choice of U, soft-update policy, reserved backup state and path stretch is a tradeoff, but its elements overlap PNNI QoS aggregation and modern resilient/dynamic TE.

### 4.4 A minimal three-epoch accounting example

One demand travels from a to b. Internal costs are [1, 100, 1]; bypass always costs 10.

There are three simple decisions:
- always internal: path-cost sum 102; no route-choice updates;
- always bypass: path-cost sum 30; no route-choice updates;
- choose instantaneous cheapest: path-cost sum 12; 2 switches.

An objective cost = path-cost sum + c*(route-choice switches) picks the last strategy only when 12 + 2c < 30, i.e. c < 9, among these policies.

For c >= 9, the fixed bypass is no worse; for c < 9, switching is better.

These numbers are merely a transparent analytical toy (not actual packets or performance measurements). The same tradeoff is available to the hierarchical policy baseline. It is **not** a NetSynth win.

If link delay changes have to be discovered, detection and metric-update work must be charged too; the example intentionally assumes those observations are already available.

## 5. Endpoint/Channel overlap

LISP already distinguishes endpoint IDs and routing locators, supported by a mapping system.

HIP supports host identities based on cryptographic identities and changing addresses; RFC 8046 explicitly supports one or both hosts changing addresses.

SCTP offers reliable message delivery, optionally unordered messages and multihoming.

QUIC connection IDs separate transport state from the 5-tuple for defined migration scenarios; QUIC v1 has restrictions on server-initiated migration.

Hence v0.1 may represent a *more coherent unified system* and may allow cleaner implementation free of backward compatibility, but the semantics above do not by themselves certify new capability.

Novelty would require proving a property **of the interactions** not attainable with comparable components, or a strict resource separation under well-specified implementation constraints.

## 6. Fair research test requires equal feasibility sets

If a comparison allows NetSynth:
- any local topology knowledge;
- an arbitrary programmable local binding engine;
- the same hierarchical controllers;
- stable external contracts;
- local repair;
- custom packet encodings;

but forces "IP baseline" to:
- flood flat OSPF;
- support only destination FIB;
- ban BSID/pathlets;
- carry legacy encapsulation with no ability to adjust;

then a large NetSynth gain is real for those selected products but **not evidence of a fundamental architectural advantage**.

Compare both:
1. deployable strong stacks under real constraints (engineering value);
2. matching abstract resource/action budgets (architectural value).

The best modern-baseline comparison may tie at the abstract level and differ substantially in production cost. Keep these claims separate.

## 7. What has survived?

Survives as clean, useful systems architecture:
- explicit ownership/lifetime separation;
- exact-version, fail-closed control;
- fixed ingress packet budget;
- unified identity/transport/forwarding layering;
- avoid dependence on historic packet formats;
- flat fallback when aggregation is not economical.

Does not survive as a **demonstrated new research contribution**:
- hierarchical opaque paths;
- local hidden restoration;
- stable token under repair;
- threshold external cost updates;
- generic joint optimization of path quality and updates;
- identity-location separation;
- unordered reliable messages.

Potentially open but currently *unproven* research deltas:
- an implementation-level forwarding/state/header Pareto separation under a **concrete limited ASIC instruction set**;
- a distributed update consistency guarantee under strict no-synchronized-epoch and bounded context constraints;
- a formal compositional service-level guarantee with substantially lower *total* state than known topology-aggregation methods;
- a genuinely new communication primitive or security/trust architecture not expressible by existing endpoint/routing methods.

None of these is adopted as the answer merely for being different-sounding.

## 8. Decision

**Research gate: FAIL for v0.1 as currently advertised.**

Interpretation: no demonstrated original architectural advantage over the best available family of techniques; not a judgment that the design is invalid.

Recommended action:
1. Preserve frozen v0.1 as a reference/systems synthesis artifact.
2. Stop trying to win by reproducing known mechanisms in a new stack.
3. Do not commission full NetSynth/XDP or a broad routing simulator to manufacture novelty.
4. Revisit the *original clean-slate goal* and select a specific capability/constraint that modern networking lacks; run a narrow prior-art and impossibility audit before adopting it.
5. If the user values an engineered clean network over a novel paper, proceed with a real prototype but honestly label the outcome an integrated system, not a new theory.

We should not keep adding layers or optimizers to preserve the project at all costs.

## References

- Chiesa et al., Intra-domain routing with pathlets, Computer Communications 2014: https://www.sciencedirect.com/science/article/abs/pii/S0140366414000978
- RFC 8402 Segment Routing Architecture: https://www.rfc-editor.org/rfc/rfc8402
- RFC 9256 Segment Routing Policy Architecture: https://www.rfc-editor.org/rfc/rfc9256
- Chang & Hwang, Dynamic Routing Information Update Policies for Hierarchical QoS Routing (2002): https://scholar.nycu.edu.tw/en/publications/dynamic-routing-information-update-policies-for-hierarchical-qos-/
- Jaumard et al., Segment Routing Traffic Engineering with Time-Based Reconfiguration Constraints, submitted 2026-10-03: https://arxiv.org/abs/2610.04759
- LISP data/control plane, RFC 9300 and RFC 9301: https://www.rfc-editor.org/rfc/rfc9300 and https://www.rfc-editor.org/rfc/rfc9301
- HIP mobility, RFC 8046: https://datatracker.ietf.org/doc/rfc8046/
- SCTP, RFC 9260: https://www.rfc-editor.org/rfc/rfc9260
- QUIC, RFC 9000: https://www.rfc-editor.org/rfc/rfc9000
