# NetSynth Architecture v0.1

> Status: consolidated current architecture.
>
> This document is the primary architectural entry point for NetSynth after the Scale-4/5/6, Security Floor, and Routing Scope lifecycle freezes.
>
> Historical phase documents remain useful derivation records, but they do not override this document or the corresponding freeze reviews.

# 1. Project goal

NetSynth is a clean-slate computer-network architecture project.

Its question is:

> If compatibility with Ethernet/IP/TCP/BGP/DNS and other deployed protocol semantics were not required, how should a modern general-purpose computer network be structured?

Clean-slate does **not** mean ignoring established theory or mature systems work.

The research method is:

~~~text
architecture question
    -> theory / prior-art reconciliation
    -> explicit architecture choice
    -> minimal semantic validation
~~~

The project avoids two failure modes:

1. rediscovering mature routing/graph theory through simulator sweeps;
2. turning the simulator into a universal routing-framework abstraction and confusing that with the NetSynth architecture.

# 2. Core design principle

The strongest principle that has emerged is **lifetime and knowledge separation**.

Different information changes at different rates and belongs at different scopes.

Conceptually:

~~~text
stable Endpoint identity
        |
Endpoint attachment Binding
        |
topology-dependent Locator
        |
compiled route state
        |
Scope transit contract
        |
local path realization
        |
physical link / queue state
~~~

Faster-changing state should usually have:
- smaller ownership scope;
- smaller propagation radius;
- less ability to invalidate slower-lived state.

A second core principle is:

~~~text
Scope hierarchy = knowledge / control / ownership hierarchy
physical path    = arbitrary graph path
~~~

The hierarchy does not constrain legal route geometry.

# 3. Scale 0-3: minimal forwarding substrate

The earliest derivation remains valid.

## 3.1 Point-to-point

A direct link requires:
- finite transfer boundaries;
- finite buffering;
- local flow/backpressure handling.

No global address is intrinsically required.

## 3.2 Branching

Once a forwarding device has several possible outputs, forwarding choice and a destination/selector concept become necessary.

Addressing appears because a choice exists.

## 3.3 Mesh

Multiple physical paths introduce routing and multipath choice.

The network is always modeled as an arbitrary physical graph.

## 3.4 Dynamic mesh

Failure/recovery introduces a routing-control function distinct from data forwarding.

Local failures should be absorbed locally where possible.

A finite Hop Budget remains the common bound against pathological transient forwarding under inconsistent control state.

# 4. Scale 4: large-scale routing

Scale 4 addresses the point where full topology or per-destination routing state everywhere becomes too expensive.

The architecture introduces:

- Routing Scope;
- Structured Locator;
- Boundary Transit Graph;
- Scoped Transit Pathlet;
- scoped route resolution;
- packet-carried route state.

## 4.1 Routing Scope

A Routing Scope is a connected control/knowledge ownership region.

It is not:
- an AS;
- a subnet;
- an administrative organization;
- a mandatory routing tree.

Scopes are laminar within one layout generation.

A Scope owns detailed information internally and exposes only bounded contracts to its parent.

## 4.2 Structured Locator

A Locator identifies a topology-dependent forwarding position.

Its structure follows the Scope/control lineage sufficiently to let large-scale routing reason at coarse resolution.

A Locator is not a stable Endpoint identity.

## 4.3 Boundary Transit Graph

A child Scope exports a Boundary Transit Graph (BTG).

BTG vertices are real boundary interfaces.

BTG edges are Scoped Transit Pathlets (STPs).

## 4.4 Scoped Transit Pathlet

An STP is an opaque reusable transit service:

~~~text
ingress boundary
    -> owner-local hidden realization
    -> egress boundary
~~~

The parent does not know the internal realization.

A parent may compose its own pathlets using:
- immediate-child STPs;
- physical crossing links visible at the parent level.

It may not directly inspect arbitrary descendant topology.

A pathlet generation remains valid while its hard external semantics remain valid.

Soft routing metrics may change independently.

## 4.5 Change containment

If an STP can repair itself internally while preserving its hard contract, no parent-visible hard update is required.

If the hard contract fails, that generation is withdrawn and stale references fail closed.

No global routing epoch is required.

## 4.6 Route resolution

Persistent routing summaries are pushed upward:

~~~text
child Scope
    -> parent
    BTG / STP contracts
~~~

Destination-specific routes are pulled on demand:

~~~text
ingress
    -> relevant Scope Route Services
    -> compiled route
~~~

This avoids both:
- global pathlet flooding;
- global destination-specific state in every transit router.

## 4.7 Route path geometry

The route computed over Scope summaries may:
- enter a child;
- leave it;
- later re-enter it;
- cross sibling Scopes in any physically valid way.

Scope ownership never imposes prefix-monotone forwarding.

## 4.8 Packet-carried forwarding state

The current architecture requires some bounded packet-carried route state because transit routers do not retain all destination-specific choices.

However, the concrete wire representation is **not yet frozen**.

The earlier literal Transit Stack model is now treated as one possible implementation.

The current open abstraction is:

~~~text
Abstract Route Program
        |
        v
Compiled Forwarding Program
~~~

Compilation trades among:
- packet route-code bits;
- installed reusable forwarding state;
- writable packet context;
- forwarding work/lookups;
- path quality.

This is the main unresolved data-plane design question in v0.1.

# 5. Routing Scope lifecycle

The Scope lifecycle is frozen semantically.

## 5.1 Formation

A Scope is formed to keep control cost manageable.

Important dimensions are:
- local controller/state cost;
- parent-visible summary size;
- exported hard-contract churn;
- structural migration cost.

The architecture does not freeze one partition algorithm or one objective function.

## 5.2 Noncompressible regions

Hierarchy is optional compression.

If a region cannot be partitioned without large boundaries/high churn/little control benefit, it remains flat.

No fake hierarchy is created merely to preserve a design assumption.

## 5.3 Structural change

A stable Scope may have versioned child layouts:

~~~text
Layout g1
Layout g2
~~~

Each generation is independently laminar.

For planned changes:

~~~text
prepare g2
    -> g1 + g2 coexist
    -> publish old + new Locators
    -> move new route compilation to g2
    -> drain g1
    -> retire g1
~~~

No network-wide configuration epoch is required.

## 5.4 Structural renumbering

Changing a Scope layout may change Locator lineage.

Endpoint identity does not change.

Scale-5 Binding absorbs the renumbering.

# 6. Scale 5: Endpoint identity and mobility

Scale 5 separates identity from location.

## 6.1 Endpoint ID

An Endpoint ID (EID) identifies a logical communicating Endpoint.

It is:
- stable relative to attachment changes;
- topology-independent;
- opaque to routing.

Conceptually:

~~~text
EID = who
Locator = where
~~~

## 6.2 Endpoint Binding

A versioned Endpoint Binding maps:

~~~text
EID -> LocatorSet
~~~

The LocatorSet may contain:
- one Locator;
- several Locators for multihoming;
- temporarily no Locator during break-before-make movement.

Mobility and multihoming are the same state model: changes in the active LocatorSet.

## 6.3 Binding Service

Bindings are stored in a flat-key sharded authority system with resolver/edge caches.

The architecture requires:
- bounded authoritative replication;
- per-EID ordered versions;
- normal cached lookup;
- explicit fresh lookup after stale evidence.

It does not freeze:
- one DHT;
- one consensus algorithm;
- one replica placement scheme.

## 6.4 Safe stale mappings

A stale binding may route toward an old attachment.

Final local delivery checks the stable EID.

If that EID no longer exists at the attachment, delivery fails.

A stale mapping may reduce liveness, but it must not silently deliver to another Endpoint.

## 6.5 No global EID routing table

Transit routers do not maintain EID-to-Locator mappings.

EID resolution is an edge/control function.

# 7. Scale 6: reliable communication

Scale 6 introduces a stateful Channel because end-to-end reliability requires persistent cross-packet state.

## 7.1 Channel identity

A Channel is semantically bound to stable Endpoint identities, not Locators.

The same EID pair may own multiple Channels.

Endpoint-local opaque Receive Tokens demultiplex them.

No transport port namespace is required in the common architecture.

## 7.2 Message-oriented transport

The native reliable service is:

~~~text
Channel
    -> bounded Messages
~~~

not a global ordered byte stream.

Message boundaries are preserved.

A later completed Message may be delivered while an earlier Message remains incomplete.

No Stream/Lane/Subchannel abstraction is currently part of the common transport.

## 7.3 Packet Number and Message ID

The architecture separates:

~~~text
Message ID    = logical reliable data
Packet Number = one transmission attempt
~~~

Retransmission keeps the Message identity but uses a new Packet Number.

## 7.4 Flow control and congestion control

Receiver flow control protects Endpoint memory and is Channel-wide.

Congestion control protects path/network resources and is path-specific.

The exact congestion algorithm is not frozen.

The network may expose a small transit-mutable congestion mark, which is echoed back in authenticated transport feedback.

## 7.5 Path State

A Channel survives path replacement.

Channel-wide state includes:
- Endpoint identity;
- Receive Tokens;
- reliability/message state;
- flow control.

Path-specific state includes:
- selected Binding/Locator;
- Route Program;
- RTT/loss;
- congestion state;
- usable packet size.

When the path changes, Channel identity/reliability survive while path-performance state is replaced.

## 7.6 No concurrent multipath yet

Multihoming provides alternate paths and migration/failover.

The common Channel currently uses one active sending path per direction.

Concurrent multipath scheduling/coupled congestion is deferred.

# 8. Security Floor

Security is a cross-cutting minimum trust layer, not another network Scale.

Its purpose is only to make the existing EID/Binding/Channel claims meaningful in an adversarial environment.

## 8.1 Self-certifying EID

Conceptually:

~~~text
Identity Anchor
    |
    +-- hash -> EID
~~~

The Identity Anchor is long-lived.

It delegates shorter-lived operational roles.

## 8.2 Operational roles

Minimum roles are:
- Binding update authorization;
- Channel authentication.

Routine operational-key rotation does not change EID.

## 8.3 Signed Bindings

Binding records are independently verifiable signed objects.

Resolvers/storage are needed for storage and availability, but are not trusted to invent authentic LocatorSets.

## 8.4 Channel security

Channel establishment uses a standard authenticated key exchange whose transcript binds:
- both EIDs;
- both Receive Tokens;
- protocol context.

It deliberately does not bind Locator or Route Program.

Established Channel data/control uses authenticated encryption.

## 8.5 Explicit limits

The Security Floor does not define:
- human/service identity;
- Web-style PKI governance;
- privacy/anonymity;
- Byzantine routing security;
- revocation/transparency infrastructure;
- hardware attestation.

These are outside v0.1 unless later requirements force them.

# 9. Naming and service discovery boundary

Human/application service naming is above the NetSynth common core.

Conceptually:

~~~text
Service Reference
    -> candidate EID(s)
    -> Binding
    -> Locator(s)
~~~

A service may resolve to several EIDs.

One EID may resolve to several Locators.

These are different layers.

NetSynth does not define one mandatory global service-name hierarchy.

# 10. Group communication boundary

The common semantic floor remains point-to-point:

~~~text
Endpoint <-> Endpoint Channel
~~~

Group communication can be built as an overlay of ordinary Channels.

Network multicast/replication and HPC/AI collective offload remain optional future acceleration capabilities, not common correctness primitives.

# 11. Packet size and packetization

Forwarding nodes do not fragment transport packets.

Endpoints packetize Messages according to path-specific usable packet size.

A common Base Packet Size is required conceptually so bootstrap/control traffic has a portable floor.

Larger usable sizes should be learned end to end using packetization-layer probing principles.

Packet-size state belongs to Path State.

## 11.1 Open dependency on forwarding-program compilation

The packetizer must know the final compiled routing overhead before transmission.

Therefore a packet's payload budget is conceptually:

~~~text
usable path packet size
    - network envelope
    - compiled route-code bytes
    - reserved writable forwarding context
    - Channel framing
    - authenticated-encryption overhead
    = Message payload
~~~

The packet wire size must not grow without bound after ingress.

The exact forwarding-program representation is still open.

# 12. Current unresolved architectural question

The forwarding-program representation now has an architecture choice: **hybrid compiled forwarding**. The choice is specified in `docs/forwarding-program-architecture.md` and awaits minimal semantic validation before freeze.

The selected model contains:
- finite Packet Route Code carrying coarse destination-specific choices;
- reusable Scope-local forwarding bindings for STPs/subprograms;
- bounded writable Forwarding Context reserved before transmission;
- a compiler that trades packet bits against persistent local state and hardware limits.

The exact byte encoding remains an implementation/profile choice. The next step is minimal semantic validation against packet-heavy and state-heavy controls.

# 13. Architecture versus implementation

The following are architecture semantics:
- Scope knowledge boundaries;
- STP opacity and generation safety;
- EID/Locator separation;
- Binding version semantics;
- reliable unordered Message Channel;
- path/Channel state separation;
- minimum security trust chain.

The following remain implementation/research choices:
- graph partition algorithm;
- compact-routing construction;
- exact Route Program encoding;
- Binding-Service sharding/consensus;
- congestion-control algorithm;
- PMTU probing algorithm;
- cryptographic suite;
- exact wire format;
- numeric field widths.

# 14. Historical work

Phase 1-5 experiments remain valuable historical evidence.

They helped expose:
- hidden global-topology oracles;
- state/stretch trade-offs;
- hierarchy distortion;
- attachment-state explosion;
- poor behavior on expander/noncompressible graphs.

However, their prefix-monotone routing and metric-aware hierarchy choices are not current NetSynth architecture.

Historical experiment code should remain available as regression/research infrastructure, but new architecture work should not continue those phases by default.

# 15. Project status

The following areas are semantically frozen unless a later requirement exposes a contradiction:

- Scale 0-3 minimal forwarding principles;
- Scale-4 Scope/STP/routing information ownership;
- Scope lifecycle and structural evolution;
- Scale-5 Endpoint identity/mobility;
- Scale-6 reliable Message Channel;
- minimum Security Floor;
- service naming boundary;
- group communication boundary.

The current active work is:

> minimal semantic validation of the selected hybrid compiled forwarding model.

Do not reopen the architecture choice unless that validation exposes a contradiction.
