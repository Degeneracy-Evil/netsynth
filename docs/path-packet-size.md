# Path Packet Size and Endpoint Packetization

> Status: architecture choice.
>
> This document closes a semantic gap already created by Scale 6:
>
> forwarding nodes never fragment transport packets, but the sender must know how large a packet the current path can actually carry.

## 1. Prior-art reconciliation

IPv6 already chooses source-only fragmentation rather than router fragmentation.

Path MTU Discovery identifies the minimum link MTU along a path.

Packetization-Layer PMTU Discovery (PLPMTUD / DPLPMTUD) goes further: the layer that packetizes transport data actively probes packet sizes and confirms successful end-to-end delivery. This avoids depending on reliable delivery of router-generated "packet too big" messages.

The relevant lesson for NetSynth is:

> packet-size discovery belongs with endpoint packetization/path state, not with persistent routing identity.

## 2. Architecture choice: no transit fragmentation

A NetSynth forwarding node never splits one network packet into several network packets.

If a packet cannot be forwarded as one unit on the selected next-hop service, it is not transparently fragmented by the network core.

Reasons:
- fragmentation state would be introduced into transit;
- reassembly would need another location/lifetime rule;
- loss of one fragment amplifies work;
- path changes complicate fragment semantics;
- Scale-6 Endpoints already know Message boundaries and can repacketize/retransmit correctly.

Large Messages are segmented into transport packets at Endpoints.

## 3. Common minimum packet capability

Every NetSynth path must support a common **Base Packet Size** at the network layer.

The exact byte value is not frozen yet.

A physical/link technology unable to natively carry one Base-size network packet must provide adaptation below the NetSynth network layer, or it is not directly usable as a NetSynth link.

This gives:
- control/bootstrap packets a portable size floor;
- a safe initial packetization size before path probing;
- graceful operation when no PMTU optimization is implemented.

This is analogous in purpose, not wire compatibility, to an internetwork minimum MTU.

## 4. Path Packet Size is Path State

Scale 6 Path State is extended conceptually with:

~~~text
usable_packet_size
probe_state
~~~

The value is associated with the current delivery path:

~~~text
selected Locator
Route Program
path-generation/local epoch
~~~

It is not:
- Endpoint identity state;
- Channel-wide reliability state;
- an EID Binding property.

When a genuinely new path is selected, packet-size knowledge starts conservatively unless the implementation has valid cached evidence for an equivalent path.

## 5. Endpoint probing is authoritative

The sender starts from Base Packet Size and may send larger **probe packets**.

A probe succeeds only when endpoint-visible transport feedback confirms that this exact transmission reached the peer over the relevant path.

On success:

~~~text
usable_packet_size may increase
~~~

Repeated evidence that the current size is not usable may cause:

~~~text
usable_packet_size decreases
repacketize still-needed Message data
retransmit under new Packet Numbers
~~~

The exact search/loss-classification algorithm is not frozen.

DPLPMTUD-like algorithms are preferred implementation prior art.

## 6. Probe packets obey congestion control

A PMTU probe is not free traffic.

It is sent under the active Path State's congestion/pacing policy.

A probe failure is not automatically proof that the packet was too large:
- it may have been congestion loss;
- route state may have failed;
- the peer may have moved.

The endpoint packetization algorithm must therefore be conservative when interpreting loss.

## 7. Route migration

Suppose Path A supports large packets and the Channel migrates to Path B.

NetSynth does not copy Path A's usable packet size blindly into B.

Conceptually:

~~~text
Channel reliable Message state
        survives

old Path A packet-size state
        remains old-path state

new Path B
        starts from safe base / validated cached hint
        probes upward
~~~

Outstanding logical Message ranges can be repacketized on B under new Packet Numbers.

This directly composes with the frozen Scale-6 retransmission semantics.

## 8. No pathlet MTU requirement beyond the base floor

Every valid STP must be able to carry the common Base Packet Size.

NetSynth does **not** require every STP to publish its exact maximum packet size as part of the parent-visible hard contract.

Doing so would:
- enlarge BTG contract state;
- make internal link-MTU changes propagate upward;
- couple endpoint packetization to hierarchy summaries.

Larger-size capability is learned end to end.

An implementation may provide a soft upper-bound/hint from routing/control state to accelerate probing, but correctness must not depend on it.

## 9. Optional local Too-Large feedback

A forwarding element that drops a packet because of a local size limit may optionally return an advisory "too large" indication with a supported-size hint.

The common architecture does not require this feedback for correctness.

Reason:
- such feedback may be lost;
- it may be spoofed by an on-path participant;
- the sender can recover using endpoint probing.

The hint may accelerate downward adjustment but must not be the only packet-size discovery mechanism.

No generic ICMP-like error subsystem is introduced here.

## 10. Security boundary

Packet-size probing is an availability/performance mechanism.

An on-path attacker can:
- drop large probes;
- forge pessimistic advisory hints if such hints are accepted unauthenticated.

This can reduce throughput but cannot change EID/Channel identity or protected payload contents.

The attacker could already cause denial by dropping traffic.

Therefore the Security Floor does not need a new global router-authentication mechanism merely for PMTU.

## 11. Effective application payload size

The transport/application usable payload is smaller than the network packet size because of:

- network envelope;
- Route/Transit Stack;
- Channel framing;
- AEAD tag;
- other endpoint headers.

The sender packetization layer must account for the actual current header overhead.

Thus:

~~~text
usable_message_fragment
    <= usable_packet_size - current_header_overhead
~~~

A longer Route Program can reduce per-packet application payload.

This makes Route-Program header cost operationally visible rather than merely a byte-count statistic.

## 12. Variable header overhead

Because NetSynth Route/Transit Stack length may vary across paths and recursive execution, packetization must use a conservative bound for the packet instance being emitted.

A packet must never assume that downstream routing expansion can grow it beyond the supported network packet size.

Therefore Transit-Stack execution uses ingress-reserved packet header space.

The selected forwarding architecture in `docs/forwarding-program-architecture.md` gives each compiled route a finite Packet Route Code plus bounded writable Forwarding Context. STPs expose representation-independent hard resource requirements, and the compiler reserves enough packet-resident context before packetization.

The exact wire encoding is still deferred, but **in-flight routing operations may not increase packet wire length beyond that ingress reservation**.

## 13. Raw best-effort packets

A raw Scale-5 sender without a reliable Channel can still use packet-size probing, but it needs some endpoint confirmation mechanism for successful probes.

If it has none, it must stay at Base Packet Size or rely on explicitly provided path-size information.

The network core does not promise to infer PMTU on behalf of an unacknowledged application.

## 14. State lifetime

Packet-size state now fits the existing hierarchy:

~~~text
Endpoint ID
Channel
Message/reliability state
Binding / Locator
Path State:
    Route Program
    RTT / congestion
    usable packet size
STP realization
physical link state
~~~

A path-size change does not invalidate Endpoint/Channel identity.

## 15. What is not frozen

This architecture does not freeze:

- exact Base Packet Size in bytes;
- probe-search algorithm;
- probe timing;
- black-hole detection thresholds;
- router Too-Large message format;
- PMTU cache sharing between Channels;
- exact packet/header wire format;
- jumbo-frame policy.

These are implementation/profile choices.

## 16. Minimal semantic validation

A tiny prototype should validate only:

1. Base Packet Size works without any PMTU discovery;
2. a Channel can probe and raise usable packet size after endpoint-confirmed success;
3. a too-large/lost probe does not corrupt Channel reliable state;
4. Message data can be repacketized under new Packet Numbers after size reduction;
5. path migration preserves Message state but resets/replaces packet-size Path State;
6. no transit fragmentation/reassembly state exists;
7. STP/BTG hard contracts need only guarantee Base Packet Size;
8. optional advisory Too-Large feedback is not required for recovery;
9. current Route/Transit header overhead is charged against payload size;
10. routing-stack execution cannot cause packet size to exceed its ingress-reserved header budget;
11. STP forwarding-resource requirements are composed without opening descendant realizations;
12. repair within the advertised hard resource requirement preserves generation, while a repair requiring greater packet/context capability cannot silently keep the same hard contract.

Do not benchmark PMTUD algorithms or link MTU distributions.

## 17. Next step

The packet-size semantics are sufficiently specified for minimal validation.

Do not design the complete wire format before this invariant is tested against the existing Route/Transit Stack model.
