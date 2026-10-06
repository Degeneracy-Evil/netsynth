# Forwarding Program Freeze Review

> Reviewed implementation: `f56a47bad0bc8b638b54b91f075572f7743c7108`.
>
> Decision: **the NetSynth hybrid compiled forwarding-program semantics are frozen.**
>
> This freeze covers information placement and bounded execution semantics. It does not freeze a byte-level wire format, token width, hardware pipeline, compiler heuristic, or forwarding performance claim.

## 1. Selected model

NetSynth uses a hybrid compiled forwarding model:

~~~text
Abstract Route Program
        |
        v
Compiled Forwarding Program
        |
        +-- finite Packet Route Code
        +-- bounded writable Forwarding Context
        +-- reusable Scope-local forwarding bindings
~~~

Packets carry coarse destination-specific choices.

Scopes retain reusable local forwarding state for opaque STPs/subprograms.

The compiler explicitly trades packet bits against local installed state and target forwarding resources.

## 2. Validation result

The prototype validates the selected model against packet-heavy and state-heavy controls on the same abstract route.

It demonstrates:

- identical physical route semantics before repair;
- identical repaired route semantics after hidden local repair;
- no descendant physical path in hybrid packet code;
- parent compilation through immediate-child public contracts only;
- fixed packet wire size after ingress;
- bounded writable context;
- context shortage spilling into additional reusable local bindings;
- no per-flow/per-Channel transit state;
- exact-generation stale references failing closed;
- hard resource growth requiring a new STP hard generation;
- hidden local repair preserving outer hybrid route code.

No blocking hidden topology dependency or packet-growth operation was found.

## 3. Resource trade-off is real

The semantic fixture exposes the intended trade:

- packet-heavy encoding uses little installed state but large packet route code and must recompile after hidden physical repair;
- state-heavy encoding minimizes packet code but installs more forwarding state;
- hybrid encoding keeps coarse packet code while using bounded context and reusable local bindings.

The concrete byte figures are only a declared accounting profile, not a wire-format claim.

The architecture freezes the resource dimensions, not their current weights or widths.

## 4. Scope opacity

The hybrid compiler can be given child interfaces exposing only:

- public STP advertisement;
- hard forwarding-resource requirement;
- opaque install operation.

It does not require child registry or graph access.

Only the owning Scope sees the physical realization it compiles.

Thus:

~~~text
parent route code
    !=
descendant physical path
~~~

remains enforced.

## 5. Fixed packet size

Packetization occurs after forwarding compilation.

Ingress knows:

~~~text
usable packet size
- Packet Route Code
- reserved Forwarding Context
- network / Channel / security envelope
= payload capacity
~~~

Runtime forwarding mutates only the pre-reserved context.

No forwarding operation may enlarge packet wire length.

If a program cannot fit the packet/context capability, compilation or packetization rejects it or uses a more state-heavy representation.

## 6. Local repair

An STP may keep its generation when the new internal realization preserves:

- ingress/egress hard semantics;
- exact token/generation meaning;
- advertised forwarding-resource requirement.

The local binding implementation may change while outer packet route code remains unchanged.

If the required forwarding resource grows beyond the hard contract, the same generation cannot be retained.

## 7. In-flight packet semantics during same-generation repair

The validation prototype executes before or after a converged repair and does not model concurrent packet/table update.

The architecture resolves that lifetime boundary as follows:

> same-generation repair guarantees preservation of the **external STP contract and future outer-route compilation**, not lossless survival of every packet already executing the old internal realization.

A packet that has not yet entered the repaired STP can use the stable entry token and follow the new realization.

A packet already inside the old realization may hold a local continuation reference that is retired by the repair. Such a reference must:

- fail closed if no longer valid;
- never alias a replacement meaning.

Reliable Channel semantics above the network already handle ordinary packet loss/retransmission.

Therefore the common architecture does **not** require:

- draining all in-flight packets;
- per-binding reference counts;
- per-packet router state;
- multi-version continuation tables.

An implementation/profile may provide graceful draining if useful, but it is not required for correctness.

## 8. Binding/token lifetime

Scope-local forwarding tokens are reusable forwarding-state handles, not identity.

They must obey:

- exact owner-local interpretation;
- no accidental reuse/alias while stale references may exist;
- fail-closed lookup when retired.

The current semantic implementation uses monotonic local allocation, which is sufficient for the prototype but is not a frozen production allocation scheme.

## 9. Freeze boundary

Do not reopen the forwarding-program architecture merely to optimize encoding size.

In particular, do not make any of the following mandatory common semantics:

- full physical source route in every packet;
- pure stateless-core forwarding;
- pure destination-FIB forwarding;
- literal recursive label-stack growth;
- arbitrary packet virtual machine;
- per-flow installed forwarding paths;
- algebraic route IDs;
- probabilistic Bloom-filter forwarding.

These remain implementation/profile/baseline possibilities where appropriate.

## 10. Deferred implementation choices

Not frozen:

- exact packet encoding;
- token bit width;
- cursor/context encoding;
- compiler optimization algorithm;
- admission/eviction/GC policy for local bindings;
- transactional table-update mechanism;
- hardware pipeline realization;
- forwarding throughput/latency;
- exact packet-size probing algorithm.

## 11. Result

The Scale-4 data plane can now be summarized as:

~~~text
Destination Locator
Hop Budget
finite Packet Route Code
bounded writable Forwarding Context
payload

+

Scope-local reusable forwarding bindings
~~~

This closes the main unresolved v0.1 data-plane architecture question.
