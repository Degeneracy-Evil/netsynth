# Scale 6: Reliable Message Channel

> Status: architecture choice after theory reconciliation.
>
> Scale 5 gives stable Endpoint identity and best-effort packet delivery across changing Locators/Route Programs.
>
> Scale 6 asks:
>
> What persistent endpoint-to-endpoint communication semantics should exist when packets can be lost, duplicated, reordered, delayed, or sent over a replacement path?

## 1. End-to-end boundary

NetSynth keeps reliability out of the routing core.

The Scale-4/5 network may:
- lose packets;
- duplicate packets;
- reorder packets;
- delay packets;
- change Route Programs;
- locally retransmit or recover at links as a performance optimization.

None of those lower-level mechanisms constitute an end-to-end delivery guarantee.

Reliable delivery therefore belongs at the communicating Endpoints.

This follows the end-to-end argument: duplicate suppression, acknowledgements and recovery cannot be made complete by lower layers alone because only the endpoints know whether the intended communication result was achieved.

## 2. Prior-art reconciliation

### TCP

TCP provides one reliable, in-order byte stream.

That is simple for stream applications, but it erases application message boundaries and imposes one delivery order across the connection.

### QUIC

QUIC keeps connection state independent of lower-layer addresses through Connection IDs and splits one connection into many independent ordered byte streams. This removes head-of-line blocking between streams, but each stream is still a byte stream.

QUIC also separates packet numbers from stream offsets: a retransmission is sent in a new packet number rather than pretending it is the same packet transmission.

### SCTP

SCTP preserves application message boundaries, supports multiple streams, separates transmission reliability from stream ordering, and fragments/reassembles messages end-to-end to fit the path MTU.

### RDP

RDP explicitly explored reliable message delivery without forcing sequenced delivery when the application does not require it.

The important lesson is:

> reliability, message boundaries and delivery ordering are separate properties.

### MPTCP

MPTCP shows that concurrent multipath requires additional connection-level sequencing, reassembly and path management. NetSynth does not adopt concurrent multipath merely because several Locators exist.

## 3. Architecture choice: Channel is now forced

Scale 6 introduces a stateful endpoint-to-endpoint **Channel**.

The reason is reliability, not mobility.

A Channel owns persistent state needed across packets:

- peer Endpoint identity;
- packet transmission numbers;
- acknowledgements and loss recovery;
- message reassembly / duplicate suppression;
- receiver flow control;
- path-dependent congestion state;
- current replaceable Binding/Locator/Route material.

The Channel is endpoint state.

Transit routers keep no Channel state.

## 4. Channel identity is locator-independent

A Channel is semantically bound to:

```text
Local Endpoint ID
Remote Endpoint ID
```

and not to:
- a Locator;
- a Route Program;
- a physical path.

Those are replaceable delivery state.

Therefore movement or route replacement does not create a new Channel.

## 5. Local Channel Tokens

The same EID pair may have several Channels.

NetSynth therefore needs an endpoint-local demultiplexing identifier.

Each endpoint allocates an opaque **Receive Token** that its peer places in Channel packets destined to it.

A Channel conceptually has:

```text
local_receive_token
remote_receive_token
```

Tokens:
- are meaningful only at the receiving Endpoint;
- need not be globally unique;
- have no routing meaning;
- survive Locator changes;
- may later be rotated for security/privacy reasons.

This follows the useful part of QUIC Connection IDs without importing QUIC wire compatibility.

## 6. Channel establishment

A minimal opening exchange is conceptually:

```text
A -> B:
    OPEN {
        Source EID = A
        A_receive_token
    }

B -> A:
    ACCEPT {
        destination token = A_receive_token
        B_receive_token
    }
```

The Destination EID in the Scale-5 envelope already identifies B during OPEN.

After establishment:
- A-to-B Channel packets carry B's receive token;
- B-to-A Channel packets carry A's receive token.

The OPEN token also identifies duplicate retransmissions of the same opening attempt so they need not create duplicate Channels.

Security/authentication of Channel establishment is deferred.

## 7. No transport ports

NetSynth does not introduce TCP/SCTP-style port numbers at this scale.

An EID already identifies a logical communicating Endpoint rather than merely a host/interface.

Service discovery may later map a human/service name to an Endpoint ID.

If one application wants additional internal multiplexing, that is above the Endpoint/Channel boundary unless a later architecture question proves a common network transport abstraction is needed.

## 8. Architecture choice: message-oriented service

The standard Channel transfers **Messages**, not an undifferentiated byte stream.

A message:
- has one sender-assigned Message ID within a Channel direction;
- preserves its boundary to the receiver;
- may be larger than one network packet;
- is fragmented and reassembled only at Endpoints.

This makes application framing explicit and prevents the transport from destroying structure that applications already possess.

A byte-stream API can be built above Messages by assigning byte offsets and buffering. It is not the Scale-6 primitive.

## 9. Reliable but not globally ordered

The standard Channel attempts reliable delivery of each Message.

Within one live Channel, the receiver:
- suppresses duplicate message/fragments;
- reassembles fragmented Messages;
- delivers a completed Message at most once to the transport user.

The Channel does **not** impose one global application-delivery order across Message IDs.

A later complete Message may be delivered while an earlier Message is still missing.

This deliberately avoids connection-wide head-of-line blocking.

Applications that require ordering may encode an ordering relation above the Message service. If repeated use proves that such ordering deserves a common abstraction, it can be introduced later rather than imposed on every Channel now.

## 10. Reliability is not exactly-once application effect

Transport acknowledgement means that Channel state at the receiver accepted the relevant transport data.

It does not prove:
- the application durably stored it;
- the application acted on it exactly once;
- receiver state survived a crash.

Across Endpoint crash/state loss, exactly-once application effects require application/storage semantics such as durable IDs, transactions or idempotence.

NetSynth does not promise them at transport.

## 11. Packet Number versus Message ID

NetSynth separates transmission identity from application-message identity.

### Packet Number

Each Channel direction assigns monotonically increasing Packet Numbers.

A Packet Number describes one transmission attempt and is never reused for retransmission.

ACKs acknowledge Packet Numbers/ranges.

### Message ID

A Message ID identifies one logical application Message.

Its fragments may appear in several different packet transmissions.

If a packet is lost, necessary Message fragments/control information are emitted again in a **new** Packet Number.

This avoids ambiguity between:
- what logical data is still owed;
- which transmission event was acknowledged.

## 12. Fragmentation and reassembly

Network forwarding never fragments a Scale-6 transport packet.

The sender packetizes Message fragments to fit the current path's usable packet size.

The receiver reassembles by Message ID and fragment offset/range.

Changing Route Program or path may change future packetization.

Already-sent packet identity is never rewritten.

Large-message reassembly consumes receiver memory and is therefore covered by Channel flow control.

## 13. Receiver flow control

Reliability ACKs and receiver buffer credit are separate.

An ACK may be sent when transport data has been accepted even if the application has not consumed the completed Message.

The receiver independently advertises how much additional Channel data it is prepared to buffer.

Credit is returned only according to receiver resource policy, typically as the upper layer consumes/relinquishes buffered data.

This avoids treating acknowledgement as proof that receiver memory is free.

## 14. Congestion control is mandatory Channel behavior

A long-lived Channel is not allowed to send without congestion response on a shared network.

The architecture requires:
- sender-side congestion control;
- pacing/burst control;
- response to loss and/or explicit congestion marks;
- conservative initialization on a new path.

The exact algorithm is not a NetSynth wire semantic.

CUBIC, BBR-like, Prague/L4S-style or future controllers may be used if they obey the common congestion contract.

This is implementation algorithm choice, not a plug-in routing architecture.

## 15. Small explicit congestion signal

Scale 6 adds one small capability to the network envelope:

> a transit node may monotonically mark a packet as having encountered congestion.

The receiver echoes the congestion indication in Channel acknowledgement state.

The mark:
- is advisory/soft state;
- has no routing meaning;
- is never required for correctness;
- may cause the sender to reduce/adapt its sending rate before loss.

Exact bit encoding and queue-marking algorithm are deferred.

This borrows the architectural principle of ECN without importing IP ECN compatibility semantics.

## 16. Path state is not Channel identity

Each Channel direction has replaceable **Path State** associated with the currently selected delivery path.

Conceptually it includes:

```text
BindingVersion / selected Locator
Route Program
RTT/loss estimates
congestion-controller state
usable packet size / PMTU estimate
path validation/probe state
```

Channel-wide state includes:

```text
EID peer identity
receive tokens
Packet Number space
Message IDs
reliability/reassembly state
flow-control state
```

This separation is mandatory.

When mobility or routing changes the path:
- Channel identity remains;
- Message/reliability state remains;
- a new Path State is created or validated;
- old path RTT/congestion estimates are not blindly transferred.

## 17. No concurrent multipath yet

A Channel may switch between Locators/Route Programs and tolerate delayed packets from an old path.

Scale 6 does not yet require simultaneous scheduling across multiple active paths.

That requires additional questions:
- coupled congestion control;
- path scheduling;
- cross-path reordering;
- fairness.

MPTCP demonstrates the complexity.

Multihoming therefore gives Scale 6 rapid alternate-path availability, not automatic concurrent multipath.

## 18. Failure/liveness semantics

The Channel attempts reliable delivery while:
- both Endpoint Channel states remain alive;
- a usable path eventually exists;
- retransmission/retry policy has not declared failure.

It cannot guarantee eventual delivery under indefinite loss, permanent partition, Endpoint crash or application failure.

The Channel must therefore be able to report failure rather than claim impossible reliability.

Exact timeout/failure policy remains implementation/upper-layer policy.

## 19. Raw best-effort delivery still exists

The underlying Scale-5 packet service remains available conceptually.

It has no Channel reliability guarantee.

High-rate uses of raw best-effort delivery are still responsible for congestion response; they do not gain permission to ignore congestion merely by bypassing Channel reliability.

A future real-time requirement may justify a standardized congestion-controlled unreliable Message mode, but Scale 6 does not introduce it yet.

## 20. Resulting data envelope

Conceptually:

```text
Scale-5 network envelope {
    Destination EID
    Selected Locator
    Hop Budget
    Route / Transit Stack
    Congestion Mark
    transport payload
}

Channel packet {
    Destination Receive Token
    Packet Number
    Frames...
}
```

Possible frame semantics needed by the minimal reliable Channel include:
- OPEN / ACCEPT;
- MESSAGE fragment;
- ACK;
- FLOW_CREDIT;
- CLOSE / failure indication.

Exact wire encoding is deferred.

## 21. What Scale 6 does not yet decide

Do not yet freeze:
- cryptographic authentication/encryption;
- source-address/EID authentication;
- ordered stream abstraction;
- unreliable/expiring Channel messages;
- concurrent multipath;
- congestion-control algorithm;
- priority/scheduling API;
- application/service naming;
- transport API spelling;
- durable exactly-once delivery.

## 22. Next architecture question

The reliable Message Channel is coherent only if path change does not corrupt Channel state.

The next forced question is:

> What exact Channel/path transition semantics are required when a Route Program or Locator changes while packets, ACKs and retransmissions from the old path are still in flight?

Before fixing that state machine, reconcile with QUIC migration/loss-recovery state, MPTCP subflows, SCTP path management and packet-number semantics.
