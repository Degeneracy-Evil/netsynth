# Scale 6: Message Ordering and Multiplexing Decision

> Status: architecture choice.
>
> Question:
>
> Does NetSynth need a standard Stream/Lane/Subchannel abstraction inside every reliable Channel?

## 1. Why existing transports have streams

TCP provides one globally ordered byte stream. Independent application transactions sharing one TCP connection therefore share one delivery order.

QUIC introduces many independent ordered byte streams, eliminating head-of-line blocking *between* streams while retaining byte-stream semantics inside each stream.

SCTP preserves message boundaries and separates:
- reliable transmission;
- per-stream sequencing;
- unordered message delivery.

RDP likewise demonstrated that reliable delivery need not force sequencing.

## 2. NetSynth already removed the main reason for transport streams

The Scale-6 primitive is:

> reliable Message delivery with preserved message boundaries and no Channel-wide delivery order.

Therefore:

```text
M1 missing
M2 complete
```

does not prevent M2 from being delivered.

The Channel already supports concurrent independent application work at the Message level without creating independent ordered streams.

## 3. Architecture choice: no standard sub-Channel stream

Scale 6 does **not** introduce:
- Stream ID;
- Lane ID;
- per-stream sequence space;
- per-stream flow-control window.

The common transport abstraction remains:

```text
Channel
    -> Messages
```

not:

```text
Channel
    -> Streams
        -> bytes/messages
```

This is an explicit simplicity choice.

## 4. Ordering belongs to the consumer that needs it

An application that needs ordered records may put an application sequence number in its Messages and delay its own delivery/processing.

A byte-stream compatibility library can represent bytes as ordered chunks:

```text
StreamChunk {
    byte_offset
    payload
}
```

and reconstruct a conventional ordered stream above the Message Channel.

That buffering cost is then paid only by applications that request total order.

## 5. Message size is bounded

A Channel negotiates/advertises a finite maximum Message size.

A Message may exceed one network packet and therefore be fragmented end-to-end, but it may not consume unbounded receiver reassembly memory.

Bulk objects larger than the Message limit are represented as a sequence/set of application Messages.

This follows the original NetSynth principle that every transfer/buffer boundary is finite.

Exact maximum size is endpoint/resource policy, not a universal wire constant.

## 6. Flow-control consequence

Channel flow control accounts for buffered Message/fragments across the whole Channel.

Because Endpoint IDs identify logical communication endpoints rather than whole machines, one Channel is already narrower than a traditional host-wide transport namespace.

If a future use case shows that one logical Endpoint needs strongly isolated flow-control domains inside the same peer association, that will be a concrete reason to introduce a standard sub-Channel object.

We do not add it pre-emptively.

## 7. Opening more than one Channel is allowed

The same EID pair may establish multiple Channels, each with independent:
- reliability state;
- receiver credit;
- congestion/path state;
- lifetime.

This is heavier than an eventual lightweight substream abstraction, but it is sufficient semantically and keeps the current common model small.

Performance evidence, not analogy to QUIC, should determine whether a lighter multiplexing object is needed later.

## 8. No mandatory message ordering flag

Scale 6 also does not add a per-Message "ordered/unordered" mode.

The native service is unordered.

Applications that need ordering define it explicitly above the Message boundary.

This avoids making every sender/receiver carry transport sequencing state for a property many message-oriented workloads do not require.

## 9. Interaction with reliability ACKs

Packet ACKs and Message completion are independent of application ordering.

The receiver may acknowledge fragments/packets immediately according to reliability logic even when an upper-layer ordering wrapper is waiting for an earlier Message.

This prevents application sequencing from unnecessarily delaying transport loss recovery.

## 10. Freeze implication

Unless validation exposes a concrete ambiguity, the Scale-6 semantic prototype should contain no Stream/Lane/Subchannel class.

The minimal model should validate reliable out-of-order Message completion directly.
