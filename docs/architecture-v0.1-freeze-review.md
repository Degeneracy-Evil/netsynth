# NetSynth Architecture v0.1 Freeze Review

> Decision: **NetSynth Architecture v0.1 is frozen as a coherent semantic architecture.**
>
> This freeze is not a claim that NetSynth is production-ready or globally superior to TCP/IP. It means the current architecture has a consistent end-to-end semantic model with no known blocking contradiction.

## 1. Frozen end-to-end chain

The current architecture is:

~~~text
optional service naming
        |
        v
Endpoint ID
        |
        v
versioned Binding
        |
        v
Structured Locator(s)
        |
        v
scoped route resolution
        |
        v
Abstract Route Program
        |
        v
hybrid compiled forwarding representation
        |
        v
Scope-local STP execution
        |
        v
physical forwarding
        |
        v
exact EID delivery
        |
        v
reliable Message Channel
~~~

Security is a cross-cutting floor over Endpoint identity, Binding publication and Channel establishment/data.

## 2. Core invariants

v0.1 freezes these architectural invariants:

- identity and topology-dependent location are separate;
- Scope hierarchy owns knowledge/control/change containment, not route geometry;
- parent control consumes immediate-child contracts, not arbitrary descendant topology;
- internal repair should remain local while the external hard contract remains valid;
- destination-specific route state is resolved on demand rather than globally replicated;
- packet-carried route information and reusable local forwarding state are explicit interchangeable resources;
- packet forwarding state is bounded before transmission and packet wire length does not grow in transit;
- stale hard generations/tokens fail closed;
- reliable communication binds stable EIDs, not Locators or paths;
- flow/reliability state and path-performance state have different lifetimes;
- hierarchy is optional compression: poorly compressible regions may remain flat;
- structural Scope changes use local layout generations rather than a global network epoch.

## 3. Frozen components

The following are frozen semantically:

- Scale 0-3 minimal forwarding/routing-control principles;
- Scale-4 Routing Scope / Locator / BTG / STP / scoped route resolution;
- Scope formation and structural lifecycle;
- hybrid compiled forwarding-program information placement;
- Scale-5 Endpoint ID / Binding / mobility / multihoming;
- Scale-6 reliable unordered Message Channel;
- minimum Security Floor;
- service-naming boundary;
- group-communication boundary.

## 4. Deliberately not frozen

v0.1 does not freeze:

- exact packet/wire format;
- numeric field widths;
- one Scope partition algorithm;
- one compact-routing theorem/construction as universal route selector;
- forwarding-program compiler heuristic;
- Binding-Service storage/consensus implementation;
- congestion-control algorithm;
- path packet-size probing algorithm;
- cryptographic suite;
- multicast/collective acceleration;
- production control-plane protocols;
- hardware data-plane implementation.

These are the next engineering/research layers, not missing semantic foundations.

## 5. Important limitation

The architecture has been validated only through small semantic/adversarial prototypes and theory reconciliation.

It has **not** yet demonstrated:

- Internet-scale state cost;
- production control-plane convergence;
- hardware throughput;
- full failure behavior under asynchronous distributed implementation;
- operator deployment complexity;
- real application performance;
- superiority over optimized TCP/IP/QUIC/SCION-like systems.

Future work must test these honestly.

## 6. Research direction after v0.1

Do not immediately add more architecture layers.

The next phase should shift from "what are the semantics?" to:

> Can this architecture be realized efficiently enough to justify its additional structure?

The natural next work is implementation-oriented but still theory-aware:

- choose a concrete experimental wire/data-plane profile;
- synthesize/encode the frozen packet fields efficiently;
- implement forwarding on a realistic software or programmable-switch target;
- measure state, header overhead, lookup work, repair churn and path quality;
- compare against strong modern baselines.

Any later architecture change should be driven by a measured contradiction, not feature accumulation.
