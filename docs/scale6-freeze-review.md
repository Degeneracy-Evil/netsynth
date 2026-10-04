# Scale 6 Freeze Review

> Reviewed implementation: `faa7059d98493705369550acab66b2edc1904a80`.
>
> Decision: **Scale 6 reliable Message Channel semantics are frozen.**
>
> The freeze covers endpoint transport state/lifetime semantics. It does not freeze security, production loss detection, congestion-control algorithms, wire encoding, crash/restart recovery, bounded history reclamation, concurrent multipath, or ordered-stream compatibility.

## 1. Review result

The implementation remains a minimal semantic layer above frozen Scale 4/5.

It introduces only endpoint-local transport state:

- Channel;
- Receive Token;
- reliable Message / Message ID;
- per-direction Packet Number;
- receiver flow credit;
- replaceable per-path state;
- a soft congestion mark carried outside immutable endpoint transport integrity.

Scale-4/5 routing and identity source code remain unchanged.

## 2. Freeze criteria

All fourteen criteria from `docs/scale6-architecture-audit.md` are represented by direct implementation tests.

### Channel survives path replacement

BindingVersion, selected Locator and Route Program can be replaced while the same Channel object, EID peer identity, receive tokens, Message state, Packet Number space and flow-credit state remain alive.

### Multiple Channels per EID pair

The same Endpoint pair can establish multiple independent Channels.

Receiver-local opaque tokens distinguish them; reliability, buffer and path state do not alias.

### Stale/unknown Receive Tokens fail closed

Closing a Channel removes its Receive Token from endpoint demultiplexing.

Freshly allocated tokens are never intentionally reused. Packets for stale or unknown tokens do not enter another Channel.

### Retransmission separates Message identity from transmission identity

Lost transport data is retransmitted with:

- the same Message ID / still-needed byte range;
- a new Packet Number.

Repacketization after path/PMTU change can split the logical fragment differently without changing Message identity.

### Duplicate/reordered fragments are at-most-once delivered

Receiver reassembly accepts consistent overlap, rejects conflicting overlap, suppresses packet duplicates, and appends a completed Message to delivery order only once.

### No Channel-wide Message ordering

A later Message may complete and be delivered while an earlier Message remains incomplete.

No Stream/Lane/Subchannel ordering object is required.

### Sequence spaces survive migration

Packet Number and Message-ID allocation continue monotonically across Binding/Locator/Route-Program replacement.

Path migration does not create a new Channel sequence space.

### Flow credit is Channel-wide and ACK-independent

Receiver credit survives path migration.

Packet acknowledgement does not return receiver memory credit.

Only upper-layer Message consumption advances the cumulative receive limit.

### New path gets independent performance state

A replacement path receives new:

- RTT/variance state;
- congestion state;
- PMTU state;
- confirmation state.

It does not inherit these values blindly from the retired path.

### Late old-path ACK is isolated

Every sent data packet retains the local Path Epoch on which it was transmitted.

Late ACKs update the original path record if it still exists; after reclamation, they may satisfy logical reliability state without recreating the old path or mutating the active path.

### Congestion feedback is path-attributed

The receiver records monotonic congestion marks per received data Packet Number.

ACK feedback associates the mark with the sender's original transmission record and therefore its original Path Epoch.

Old-path congestion does not contaminate a new path controller.

### Integrity precedes Channel mutation

CRC32 is only a semantic accidental-corruption detector, not security.

Nevertheless the prototype enforces the frozen invariant:

> endpoint transport fields must pass integrity checking and structural validation before they can mutate Channel state.

Tests corrupt payload, Message metadata, Packet Number, EIDs, Receive Token, ACK state, flow credit and congestion feedback and verify no Channel mutation.

The transit congestion mark is intentionally outside this immutable checksum because forwarding nodes are allowed to set it monotonically. Its authenticated-security treatment remains deferred.

### No port / Stream / Lane / Subchannel

The prototype requires none of these abstractions.

Native service remains:

```text
Channel -> reliable unordered bounded Messages
```

### Raw Scale-5 traffic remains independent

Frozen Scale-5 Locator/EID delivery remains usable with no Channel state, and transit routing retains no Channel records.

## 3. Additional semantics verified

### Full duplex

Each Endpoint owns one Channel half for sending and receiving. The two directions have independent Packet Number, Message and path-performance state.

### Finite Message/reassembly resource

Maximum Message size is finite and receiver capacity is explicitly bounded.

The prototype conservatively reserves an entire Message's declared size on its first fragment, preventing arbitrary partial-message reassembly from exceeding receiver credit.

This reservation policy is not frozen as the only production strategy; the finite-resource invariant is.

### Empty Messages

Zero-length Messages remain real Messages and consume one accounting unit in the prototype so an unlimited number of empty incomplete/completed records cannot bypass flow control.

### Path retirement

Retired Path State can be reclaimed after:
- it is no longer active;
- no packets on it remain in flight;
- a local retention interval has passed.

Later ACKs cannot resurrect the reclaimed path.

## 4. Message-history caveat

Within one live Channel, sender Message IDs are monotonically allocated and never reused.

Before completion, conflicting overlapping data for one Message ID is rejected.

After upper-layer consumption, the prototype clears old payload bytes while retaining completion metadata. Therefore it no longer attempts to prove that an arbitrarily late *new* transmission using the same old Message ID contains byte-identical payload.

This is acceptable for the current live-Channel model because correct senders never reuse a Message ID.

A future finite-width wire design / crash-restart design must jointly specify:

- Packet-Number wraparound;
- Message-ID wraparound/reuse;
- completion-history retention;
- token/session incarnation after restart.

Do not solve this by retaining unbounded payload history in Scale 6.

## 5. Congestion-control boundary

The toy controller only exists to validate state ownership:

- conservative new-path initialization;
- bytes-in-flight accounting;
- response to deterministic loss/mark;
- pacing gate;
- path-local feedback.

No throughput/fairness claim is made.

The architecture freezes only:

> reliable/high-rate Channel traffic must be congestion responsive, and congestion state belongs to the path rather than Channel identity.

## 6. Frozen Scale-6 architecture

Conceptually:

```text
Endpoint ID
    |
    +-- Channel
          |
          +-- Receive Tokens
          +-- reliable unordered Messages
          +-- Packet Number / ACK / retransmission
          +-- receiver flow control
          |
          +-- active Path State
                  |
                  +-- Binding / Locator
                  +-- Route Program
                  +-- RTT / congestion / PMTU

Scale-5 network envelope
    |
    +-- Destination EID
    +-- Selected Locator
    +-- Hop Budget
    +-- Route / Transit Stack
    +-- Congestion Mark
    +-- Channel transport payload
```

Transit nodes have no Channel state.

## 7. Freeze boundary

Do not add more Scale-6 transport mechanisms unless a later first-principles problem requires them.

In particular, do not add by default:

- TCP-like byte-stream semantics;
- transport port numbers;
- mandatory Streams/Lanes/Subchannels;
- concurrent multipath;
- application exactly-once semantics;
- network-resident Channel state;
- a specific congestion-control algorithm;
- transport-level global path ordering.

## 8. Next architecture question

The next unresolved problem is no longer basic transport reliability.

The existing architecture still assumes opaque Endpoint IDs and unauthenticated control claims.

The next first-principles question is:

> How can an Endpoint prove that it is authorized to use an Endpoint ID, establish a Channel, and publish/modify that EID's Locator binding when the network and peers cannot trust arbitrary claims?

This is where **security identity, authentication and binding authorization** are finally forced.

Before making a NetSynth security choice, reconcile with:

- self-certifying identifiers / cryptographic identifiers;
- HIP Host Identity Tags;
- SPKI/SDSI-like authorization concepts;
- Noise/TLS 1.3 style authenticated key exchange;
- capability-oriented designs;
- LISP mapping security / authenticated mapping updates;
- SCION's control-plane trust model;
- key rotation/revocation and mobility.

Do not automatically equate Endpoint ID with a long-term public key until that architecture question is derived.
