# Transit Context Resource Budget

> Status: historical requirement discovery. The representation-specific `max_additional_transit_slots` formulation is superseded by `docs/packet-carried-routing-theory-reconciliation.md` and `docs/forwarding-program-architecture.md`. The surviving invariant is a hard, compiler-visible bound on packet-resident forwarding context.
>
> Scale 4 is not reopened as a routing-design problem.
>
> The later packet-size derivation exposed one missing hard execution invariant:
>
> an STP may recursively invoke child STPs, but a packet must not grow beyond its reserved wire size while in transit.

## 1. Problem

The frozen Transit Stack permits recursive pathlet invocation:

~~~text
parent STP
    -> invoke child STP
        -> invoke grandchild STP
~~~

If "push" literally appends unbounded header bytes in transit, then:

- ingress cannot know packet size;
- PMTU packetization is not safe;
- an internal pathlet repair could make an old packet require more header space;
- forwarding could create a packet too large for the path after the packet has already entered the network.

This contradicts the endpoint-packetization / no-transit-fragmentation architecture.

## 2. Prior-art reconciliation

MPLS / Segment Routing has the same practical problem: a head-end/controller must know whether the label/SID stack it intends to impose fits implementation limits.

Maximum SID Depth (MSD) signaling exists so path computation does not create an otherwise valid path whose label stack cannot be supported.

NetSynth adopts the same architectural lesson:

> recursive packet-carried instructions need an explicit resource bound visible to the compiler.

It does not adopt SR/MPLS wire formats or capability protocols.

## 3. Architecture choice: hard Transit Context Budget

Every advertised STP includes a hard **Transit Context Budget**.

In the semantic model this can be represented as:

~~~text
max_additional_transit_slots
~~~

meaning:

> while executing this STP, at most this many additional nested transit-label slots beyond the caller's existing route state are required.

A leaf STP realized only with physical actions may advertise zero additional slots.

A composite STP computes a conservative bound from the child pathlets it may invoke.

The eventual wire format may express the same bound in bytes or fixed-size stack entries.

## 4. Hard contract semantics

The Context Budget belongs to the STP's **hard** contract, together with:

- ingress boundary;
- egress boundary;
- handle/generation;
- realizability.

It is not a soft route-quality metric.

While an STP generation remains active:

~~~text
actual required nested context
    <= advertised Context Budget
~~~

must always hold.

An internal reroute may freely use a different realization when it remains within the existing budget.

If a new realization requires a larger bound:
- publish a new STP generation or larger hard contract;
- do not silently overflow packets compiled against the old generation.

This preserves local repair when possible while keeping old Route Programs executable.

## 5. Packet allocation

When compiling a Route Program, ingress computes a conservative transit-state capacity.

Conceptually:

~~~text
reserved slots
    =
top-level Route Program slots
    +
maximum additional nested Context Budget
      required by its selected actions
~~~

The exact formula depends on the final program encoding, but the invariant is fixed:

> every legal runtime push fits into ingress-reserved packet storage.

Transit forwarding may mutate the contents/stack pointer of this reserved area.

It may not increase the packet's wire length beyond the reserved size.

## 6. Sequential versus nested state

Two costs remain separate:

### Sequential Route Program

The number of top-level routing actions the compiled route carries.

This may grow with abstract path length.

### Nested Context Budget

Scratch/continuation space required while one composite STP recursively executes descendants.

This is bounded by the selected STP hard contracts and, structurally, by hierarchy depth.

A Route Program with many sequential STPs can therefore have a large base routing header even when each STP has small nested context.

The architecture makes both costs visible.

## 7. Parent composition

A parent does not inspect child realizations merely to compute the bound.

It consumes the child-advertised Context Budgets just as it consumes child ingress/egress hard semantics.

When building a parent STP realization, the parent can derive a conservative budget from:
- its own local action sequence;
- the Context Budgets of immediate-child STPs it explicitly invokes.

No descendant topology or hidden descendant program needs to be opened.

## 8. Knowledge/change containment

The Context Budget deliberately trades some hard summary state for execution safety.

This field should be small and stable.

An internal child change that:
- preserves ingress/egress service;
- stays within the advertised Context Budget

remains hidden.

Only an increase beyond the promised bound must propagate as a hard contract change.

## 9. Packet-size interaction

The packetization layer computes payload capacity from:

~~~text
current usable packet size
    -
network/Channel fixed overhead
    -
reserved Route Program / Transit Context bytes
~~~

Therefore packet size is fixed when the packet enters the network.

Recursive execution consumes already-reserved space rather than enlarging the packet.

## 10. Implementation limit versus pathlet requirement

Two independent limits may exist:

### STP requirement

How much nested context this STP may need.

### Forwarder capability

How much transit context a forwarding implementation can process/store.

A Route Compiler must select only a program whose reserved context fits all relevant implementation/wire limits.

The current architecture does not define capability-distribution protocol details.

A deployment may configure or advertise these limits similarly to other forwarding capabilities.

## 11. Graceful failure

If a malformed/inconsistent control plane causes an STP to exceed its advertised Context Budget at runtime:

~~~text
fail closed
~~~

It must not:
- overwrite payload;
- silently truncate route state;
- dynamically enlarge the packet.

Such an event is a contract violation.

## 12. What this amendment does not change

This does not change:

- Scope hierarchy semantics;
- path geometry;
- push-summary / pull-route resolution;
- Route Program identity;
- Endpoint/Binding/Channel semantics;
- packet-carried routing as the Scale-4 choice.

It only makes the existing packet-carried execution model resource-bounded.

## 13. Minimal validation integration

The next packet-size semantic prototype should also verify:

1. leaf STP advertises zero/small nested Context Budget;
2. composite STP budget is derived from immediate-child advertised budgets only;
3. ingress Route Program reserves enough transit slots before transmission;
4. recursive execution never grows wire size beyond that reservation;
5. internal STP repair within budget preserves generation;
6. a repair requiring more than the hard budget cannot remain the same generation;
7. insufficient implementation stack capacity rejects route compilation rather than failing unpredictably in transit.

This is part of packet-size validation, not a new Scale-4 experiment phase.
