# Scale 6 Architecture Audit

> Status: Scale-6 consolidation before minimal semantic validation.

## 1. Scale-6 architecture in one sentence

NetSynth keeps routing best-effort and endpoint-independent, then adds a full-duplex reliable unordered **Message Channel** between stable EIDs; Channel-wide reliability/flow state survives Locator changes, while RTT/congestion/PMTU/Route state is replaceable per path.

## 2. Final Scale-6 first-class objects

### Channel

A stateful full-duplex association between two stable Endpoint IDs.

It exists because reliable communication needs persistent cross-packet state.

### Receive Token

Endpoint-local opaque demultiplexing token issued to the peer.

Each direction uses the token selected by the receiving Endpoint.

It has no routing meaning and is not globally unique.

### Message

The preserved application transfer unit.

Messages are reliable and independently deliverable; Channel-wide ordering is not imposed.

### Packet Number

A monotonically increasing per-direction transmission identifier.

It identifies one transport packet transmission, not one logical Message.

### Path State

Replaceable delivery/performance state for the active sending path:

- selected binding/Locator;
- Route Program;
- RTT/loss;
- congestion controller;
- PMTU/packet size;
- congestion feedback.

It is not Channel identity.

## 3. Network-envelope addition

Scale 6 adds a small monotonic **Congestion Mark** capability to the network envelope.

A congested forwarding point may mark rather than necessarily drop an eligible packet.

The receiver returns attributable congestion information in Channel acknowledgement feedback.

Exact bit encoding/AQM is not frozen.

This is the only Scale-6 addition to the frozen routing data-plane semantics; it does not alter Scope/STP/Route-Program behavior.

## 4. End-to-end integrity requirement

A Channel packet must be end-to-end integrity checked before its contents may mutate Channel state.

The mechanism may initially be a checksum and may later be subsumed by authenticated encryption.

The architecture freezes the invariant, not the algorithm:

> corrupted ACKs, credits, Packet Numbers or Message fragments must not silently become valid Channel state.

## 5. Channel establishment

Conceptually:

```text
A -> B:
    Scale-5 Destination EID = B
    OPEN {
        Source EID = A
        A Receive Token
    }

B -> A:
    Destination EID = A
    Destination Receive Token = A token
    ACCEPT {
        B Receive Token
    }
```

After establishment:
- A sends Channel traffic to B using B's Receive Token;
- B sends Channel traffic to A using A's Receive Token.

OPEN/ACCEPT reliability/retry can use the opening Receive Token as the attempt identity in the minimal semantic model.

Security/replay-resistant authentication is deferred.

## 6. Token lifetime

Receive Tokens should be fresh opaque high-entropy values and are not intentionally reused for another live Channel.

After a Channel is destroyed, packets for its old token fail local Channel lookup.

Exact token width, rotation and replay/retirement policy belong to security/implementation work.

The common architecture does not reintroduce a TCP-style address/port TIME-WAIT identity.

## 7. No ports

Scale 6 adds no transport port namespace.

The Destination EID already names a logical communication Endpoint.

Human/service discovery can later map names to EIDs.

Multiple simultaneous Channels between the same EIDs are distinguished by Receive Tokens.

## 8. Native transport semantics

The common reliable Channel provides:

- message-boundary preservation;
- endpoint fragmentation/reassembly;
- reliable delivery attempt;
- duplicate suppression;
- no Channel-wide delivery ordering;
- finite receiver flow control;
- sender-side congestion control;
- migration/route replacement without Channel replacement.

It does not provide:
- byte-stream semantics;
- exactly-once application effects;
- concurrent multipath;
- application-level processing acknowledgement.

## 9. Message size and fragmentation

Each Channel has a finite receiver-supported maximum Message size.

Messages larger than one packet are fragmented by the sender and reassembled by the receiver.

Forwarding nodes never fragment Channel traffic.

Bulk objects larger than the negotiated Message limit are represented by multiple Messages at the upper layer.

This bounds transport reassembly resource requirements.

## 10. Packet versus Message sequence spaces

Per direction:

```text
Packet Number:
    transmission order / ACK / loss detection

Message ID:
    logical reliable Message and its fragments
```

Retransmission uses:
- same Message ID / fragment range;
- new Packet Number.

Packet Numbers and Message IDs are not reset by path migration.

## 11. Delivery semantics

Within one live Channel, a complete Message is delivered at most once to the Channel user.

Message M2 may be delivered before missing M1.

Transport receipt/ACK does not mean the receiving application durably processed the Message.

Crash/restart exactly-once semantics remain outside transport.

## 12. Flow control versus congestion control

### Flow control

Protects receiver buffers.

It is Channel-wide and survives path changes.

ACK does not automatically return flow credit.

### Congestion control

Protects the shared network.

It is sender-side and Path-State-specific.

New unrelated paths start conservatively rather than inheriting old cwnd/RTT state.

These two mechanisms must not be conflated.

## 13. Path replacement

On Route/Locator change:

### Keep

- Channel and peer EIDs;
- Receive Tokens;
- Packet Number / Message-ID spaces;
- reliable-data obligations;
- receive/reassembly state;
- flow-control state.

### Replace/reset

- Route Program;
- selected Locator as needed;
- RTT estimator;
- congestion state;
- PMTU/path packet size;
- path confirmation state.

Outstanding data from the old path may be retransmitted over the new path under new Packet Numbers.

Late old-path ACKs update only the old sent-packet/path accounting and never the new path controller.

## 14. No concurrent multipath yet

Multiple Locators are available for migration/failover.

Scale 6 has one active sending path per direction.

Temporary in-flight overlap during switching is allowed, but new data is not deliberately striped across paths.

MPTCP-like concurrent scheduling/coupled congestion is deferred until a workload forces it.

## 15. No Streams/Lanes/Subchannels

Native Messages already avoid connection-wide head-of-line delivery blocking.

Therefore Scale 6 adds no:
- stream IDs;
- per-stream order;
- per-stream flow-control windows.

A conventional ordered byte stream can be implemented above Message IDs using byte offsets.

This cost is paid only where required.

## 16. Raw best-effort service

The Scale-5 packet service still exists below Channel.

It does not acquire reliability by bypassing Channel.

A high-rate raw sender is still responsible for congestion response.

A standardized unreliable congestion-controlled Message mode may be considered later if real-time workloads force it.

## 17. State lifetime hierarchy

With Scale 6:

```text
Endpoint ID
Channel
Message / reliability state
BindingVersion / LocatorSet
Path State / Route Program
STP generation
STP internal realization
physical queue/link state
```

Not every item is strictly ordered by lifetime in every event, but the central separation remains:

- identity/reliability state survives route changes;
- path-performance state does not.

## 18. Prior-art position

NetSynth does not claim novelty for:
- end-to-end reliability;
- connection/channel IDs;
- message transports;
- packet-number ACK/loss recovery;
- ECN-like congestion marking;
- per-path congestion state;
- path migration.

The architecture choice is the combination with the already frozen EID/Locator/Scope/STP substrate:

```text
stable EID identity
+ unordered reliable Message Channel
+ endpoint-local Receive Tokens
+ packet-carried Scale-4 route state
+ replaceable per-path congestion state
+ no byte stream / no ports / no stream hierarchy
```

## 19. Known unresolved issues

Deliberately deferred:

- cryptographic Channel authentication/encryption;
- OPEN replay protection;
- source-EID authenticity;
- exact ACK format/loss detector;
- exact congestion-control algorithm;
- exact congestion-mark encoding/AQM;
- ordered stream compatibility library;
- priority/deadline/partial reliability;
- concurrent multipath;
- graceful close/restart semantics;
- application/service discovery.

## 20. Minimal semantic validation required

The Scale-6 prototype should test only:

1. one Channel survives replacement of Binding/Locator/Route Program;
2. same-EID pair can hold multiple Channels using distinct Receive Tokens;
3. packets for a stale/unknown Receive Token do not enter another Channel;
4. packet loss causes still-needed Message fragments to be emitted under new Packet Numbers;
5. duplicate/reordered fragments deliver one complete Message at most once;
6. M2 can complete/deliver while M1 is missing;
7. changing path preserves Message/Packet-number spaces and receiver credit;
8. new path uses independent RTT/congestion/PMTU state;
9. late ACK for an old-path packet cannot change new-path congestion state;
10. receiver flow credit is not released merely because a packet was ACKed;
11. corrupted transport state is rejected before changing Channel state;
12. no Stream/Lane/Subchannel or transport port object is required;
13. Scale-5 raw/Locator-only traffic remains possible without Channel state;
14. congestion mark feedback is attributable to the Path State that sent the packet.

Do not benchmark TCP, QUIC, SCTP, MPTCP or congestion algorithms.

## 21. Freeze criterion

If the minimal prototype verifies these state/lifetime semantics without introducing Channel state in transit routers or requiring byte-stream/substream machinery, freeze Scale 6.

Then return to first-principles derivation for the next problem rather than extending transport features.
