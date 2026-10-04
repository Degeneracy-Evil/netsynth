# Scale 6: Channel Path Transition Semantics

> Status: architecture choice.
>
> This document fixes how a reliable Message Channel survives Locator / Route-Program replacement while old packets and acknowledgements remain in flight.

## 1. State split

Scale 6 distinguishes two state domains.

### Channel-wide state

Survives route/mobility changes:

- Local / Remote Endpoint IDs;
- local / remote Receive Tokens;
- Packet Number space per direction;
- Message IDs;
- outstanding reliable Message-fragment obligations;
- reassembly / duplicate-suppression state;
- Channel receiver flow-control state;
- upper-layer Channel lifetime.

### Path State

Replaceable and path-specific:

- selected BindingVersion / Locator;
- Route Program;
- RTT / variance estimates;
- congestion-control state;
- usable packet-size / PMTU estimate;
- congestion-mark accounting;
- reachability/validation confidence.

This separation is a hard architecture rule.

## 2. One active sending path

Scale 6 uses one active sending Path State per Channel direction.

Changing path does not imply that all old packets instantly disappear. During a transition:

- old packets may still arrive;
- old ACKs may still return;
- retransmissions may already be scheduled;
- new application data begins using the new active path.

This temporary overlap is not concurrent multipath scheduling.

No new ordinary data is intentionally scheduled onto the retired path.

## 3. Local Path Epoch

The sender assigns each locally maintained Path State an opaque local Path Epoch / identifier.

This value is not required on the wire.

Every sent packet record stores:

```text
Packet Number
Path Epoch used for transmission
send time
bytes in flight
congestion-mark capability
frames / Message fragments carried
```

When an ACK arrives, the sender looks up the original Packet Number and therefore knows which Path State owns its RTT/loss/congestion accounting.

A late ACK from an old path must never inflate or otherwise mutate the new path's congestion controller.

## 4. Packet Number does not reset on migration

The Channel direction keeps one monotonically increasing Packet Number space across path replacement.

Example:

```text
old path: PN 100, 101, 102
switch
new path: PN 103, 104, ...
```

Late arrival of PN 101 is still unambiguous.

The receiver's ACK/deduplication logic therefore does not need a new connection or sequence space merely because the route changed.

## 5. Logical data may be retransmitted on a new path

Suppose old-path packet PN 101 carried fragments of Message M7.

If PN 101 is considered lost, the sender may emit those still-needed M7 fragments on the new path in PN 105.

Thus:

```text
Message identity != packet transmission identity
```

The receiver deduplicates by Message/fragment identity.

ACK of either valid transmission can satisfy the underlying reliable-data obligation.

This mirrors the useful separation in QUIC frame retransmission and MPTCP connection-level data numbering.

## 6. New path starts conservatively

A newly selected Locator / Route Program creates a new Path State.

By default it does not inherit:
- congestion window;
- RTT estimator;
- PMTU;
- congestion history

from an unrelated old path.

It begins from a conservative initial state and learns from new-path traffic.

An implementation may reuse path state only when it can identify the path as a recently validated equivalent path. That is an optimization, not the default semantic rule.

## 7. Path confirmation

Before treating a new path as fully established for performance purposes, the sender should obtain evidence that Channel traffic reaches the peer over it.

At this architecture level, acknowledgement of a Channel packet sent on the new Route Program is sufficient as a **reachability/performance confirmation**.

Cryptographic anti-spoof / anti-amplification path validation is a future security question and may require a stronger challenge-response protocol.

## 8. Old Path State retirement

After switching away from an old path, its Path State remains only while needed to interpret outstanding sent packets / late ACKs.

It can be reclaimed when:
- no relevant packets remain outstanding, and
- the implementation's late-packet retention window expires.

After retirement:
- late packet ACKs may be ignored for path metrics;
- they must not recreate or reactivate that Path State;
- Channel-level duplicate/reliability logic remains safe through Packet/Message IDs.

This prevents path-state accumulation across repeated mobility.

## 9. ACK path independence

An ACK is Channel control information.

It may return over the receiver's currently selected reverse path; the reverse path need not be the physical reverse of the acknowledged data path.

Therefore RTT measurement is always an observed end-to-end round trip, not a claim of symmetric physical routing.

Congestion/loss attribution still belongs to the sender's path on which the acknowledged packet was transmitted.

## 10. Explicit congestion feedback attribution

If a packet was congestion-marked by the network, the receiver reports that information in acknowledgement state strongly enough for the sender to associate it with the relevant sent packets / Path State.

The exact encoding may use marks, counters or ACK-range metadata.

The hard semantic requirement is:

> congestion observed on an old path must not be charged to an unrelated new path, and congestion marks must not be silently erased by the transport.

## 11. Flow control remains Channel-wide

Receiver buffer credit describes Endpoint memory, not a network path.

It therefore remains Channel-wide across path changes.

Migration does not reset the receiver's advertised credit or permit the sender to exceed previously established receive limits.

This matches the lifetime split:

```text
flow control -> receiver resource state
congestion control -> path resource state
```

## 12. Path-change triggers

A Channel may replace its active delivery path after:

- hard Route Program / STP failure;
- selected Locator no longer hosts the peer EID;
- fresh Binding resolution selects another Locator;
- route-quality policy chooses a new Route Program;
- explicit local mobility changes the sender's own delivery position.

The trigger does not change Channel identity.

## 13. Failure recovery order

When current delivery fails, the endpoint should preserve the Scale-5/6 distinction:

1. if the selected Locator still appears valid, try a new Scale-4 Route Program to that Locator when appropriate;
2. try another Locator from the same current Binding;
3. fresh-resolve the remote EID if attachment state appears stale;
4. create a new Path State and resume the existing Channel.

This avoids turning every route failure into an identity lookup.

## 14. Channel close is not path failure

No viable current path does not immediately mean the Channel's semantic peer identity disappeared.

The Channel may:
- wait for a new route/attachment for some policy-defined interval;
- attempt Binding refresh;
- eventually report Channel failure/close.

Exact liveness timeout policy is not a routing semantic.

## 15. Why no concurrent multipath

Scale 6 deliberately does not add:
- striping one Message across independent active paths;
- coupled congestion control;
- multipath scheduling;
- path-quality balancing.

Those are performance mechanisms, not required for reliable mobility continuity.

If later workloads justify them, they can be derived from the Channel/Path-State split without changing Endpoint identity or reliable Message semantics.

## 16. Minimal implementation invariant

For every sent packet the implementation must be able to answer independently:

```text
Which Channel data did this packet carry?
Which Path State did this transmission use?
```

These two answers must remain independent across retransmission and migration.

## 17. Next architecture question

Path migration is now semantically coherent.

The next forced issue is receiver/application concurrency:

> Is reliable unordered Message delivery alone sufficient as NetSynth's common transport service, or does the architecture itself need a standard sub-Channel ordering/multiplexing abstraction?

This must be answered before adding streams simply because QUIC/SCTP have them.

The comparison should focus on:
- common application ordering requirements;
- head-of-line blocking;
- flow-control isolation;
- cost of opening several Channels;
- whether application-level Message sequencing is sufficient.
