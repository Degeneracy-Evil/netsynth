# Scale-6 minimal semantic validation

## Reconciliation and boundary

Mathematical abstraction: endpoint reliable, unordered, bounded Messages over a lossy,
duplicating, reordering best-effort substrate, with changing delivery paths.

Closest established problems: end-to-end reliable datagrams, packet/data sequence separation,
receiver resource accounting and migration-aware per-path congestion accounting.

Known upper bounds / constructions: adopt established ACK/retransmission, range reassembly,
duplicate suppression and cumulative credit semantics, not a new reliability algorithm.
[QUIC RFC 9000, section 13.3](https://www.rfc-editor.org/rfc/rfc9000#section-13.3)
separates retransmitted information from packet transmission identity. Message-oriented
unordered delivery and the prior-art comparison are already chosen in the Scale-6 architecture documents.

Known lower bounds / impossibility: indefinite loss, permanent partition or lost endpoint state
precludes unconditional eventual delivery; transport ACK is not durable application exactly-once effect.

Why these results do not fully answer NetSynth: the residual question is composition with frozen
EID bindings and packet-carried scoped Route Programs, not transport throughput or algorithm novelty.

NetSynth-specific question: can Channel reliability and receiver resources survive replacement of
Binding/Locator/Route Program without contaminating transit routing or new-path performance state?

Minimal experiment required: one five-node chain, two existing remote attachments, a few Messages,
explicit loss, reordered/duplicate fragments, migration, late ACK/mark, corruption and stale tokens.

## Implementation

`scale6.py` has no physical-graph or Route-Service access. Endpoint-local Channel halves carry
Local/Remote EIDs, exchanged Receive Tokens, independent send Packet Numbers / Message IDs,
fragment obligations, reassembly, completion history and flow credit. The pair is full duplex.
Multiple Channels between the same EIDs have independent token, reliability and buffer state.

`establish_channel()` models a successful OPEN/ACCEPT token/resource exchange directly between
endpoint objects. This is not a new network establishment protocol. A finite maximum Message size
is agreed before use. Opening retries, timers, wire encoding and graceful closing are not modeled.
Local close removes the token from endpoint lookup; fresh tokens combine entropy with a monotonic
local allocation counter, so even deterministic repeated test entropy cannot alias retired tokens.

One active sending Path State holds binding, Locator via Route Program, PMTU budget, RTT/variance,
toy congestion window, pacing tick, in-flight bytes, marks, losses and confirmation. Every sent data
record retains its original local path epoch, time, bytes and fragment. A new path starts independently.
Retired paths can be reclaimed after outstanding transmissions resolve and a local retention interval.
Later ACKs can satisfy logical data without recreating the reclaimed path or changing the active path.

Retransmission uses still-unsatisfied byte ranges with the original Message ID and new Packet Number;
it can split a former fragment when the new PMTU is smaller. Overlap is checked and deduplicated.
Completion delivers immediately, independent of earlier incomplete Messages. No ordering mode,
stream, lane, subchannel, port or generic transport framework is introduced.

Flow credit is a cumulative committed-byte limit. The sender reserves the whole Message once;
the receiver reserves it on first fragment. This conservative policy bounds incomplete reassembly,
including one accounting unit for empty Messages. ACK never releases this reservation. Only upper-layer
consumption returns credit, and reordered feedback cannot regress the cumulative limit.

CRC32 covers endpoint transport identities, token, Packet Number and the complete fragment/control frame.
Integrity and structural checks precede Channel mutation, including packet deduplication, ACKs and credit.
The separately modeled network mark may only be monotonically set and is echoed per acknowledged data PN;
it is intentionally outside the immutable transport checksum. CRC is not authentication or cryptography.

The fixture routes opaque payload bytes through unchanged Scale 4 and exact Scale-5 EID delivery before
dispatching the corresponding packet object at the endpoint. Old-path packets are never silently sent
using the new Route Program: late originals in the workload reached the endpoint before movement and
are only processed later. Reverse ACK traffic may use the current reverse path.

## Reproduce and evidence

```bash
uv run --locked python src/scale6_main.py
uv run --locked python scripts/check.py
```

The JSON schema is `netsynth.scale6.semantic-probe.v1`; topology, deterministic injection parameters,
Message/PMTU/resource limits, toy congestion policy and all fourteen audit criteria are recorded.
There is no random sweep or throughput claim.

- M2 (ID 1) completes before M1 (ID 0); each is delivered once despite duplicates/overlap.
- Lost PN 0 is retransmitted as PN 4 and 5, with smaller new-path fragments.
- Binding changes from version 1 to 2; stale attachment delivery reports `eid_absent`, then fresh lookup
  recompiles the path while preserving the Channel, token, number spaces and credit.
- Remote credit stays 16 through ACK and migration; consuming eleven bytes raises its limit to 27.
- Old-path marks are charged only to old-path records; the new path initially has no RTT/variance,
  congestion history or inherited PMTU. New-path receipt subsequently confirms only that path.
- Corrupted data/demux/ACK/credit/mark fields leave Channel state unchanged. Unknown and retired tokens
  do not enter any other Channel, including after repeated deterministic token entropy.
- All fourteen probe criteria pass. Unit tests additionally cover atomic malformed-frame rejection,
  empty Messages, conflicting overlaps, exhausted credit, pacing/congestion gates, version regression,
  independent same-peer Channels and ACK after old-path reclamation.
- Scale-4/5 source is unchanged; their existing tests and Locator-only infrastructure probe remain valid.

## Remaining semantic / implementation limits

No accidental byte-stream delivery order, locator-as-Channel identity, or Channel state in transit routing
was found. The fourteen stated freeze criteria pass within the live-endpoint semantic model.

The documents deliberately leave establishment retry/replay, crash/restart, authenticated peer identity,
close/liveness policy, loss detection and exact congestion/PMTU algorithms unresolved. The prototype
uses explicit loss events, a conservative two-packet initial window, one data packet per logical tick
and halving on loss/mark; this is only a semantic congestion response, not a production controller.
ACK-only cumulative feedback is explicitly repeatable and does not elicit ACK loops; it is not a paced
control-packet scheduler. No automatic recovery planner or PMTU discovery is introduced.

PMTU uses a declared 64-byte model header budget for data; Python repr is checksum/opaque-fixture
encoding, **not** a real wire-size model. ACK-range compression, control packetization and bounded
Packet/Message-history reclamation remain unimplemented. Received payloads are released on consumption,
but metadata histories and sender transmission history remain retained for tiny live-Channel experiments.
Whole-Message reservation can reduce utilization; it is resource policy, not an architectural mandate.

One future clarification is how a mutable transit congestion mark is protected once authenticated
transport is introduced. It cannot simply be placed in the same immutable endpoint checksum region.
These deferred choices do not change the present state/lifetime invariants or justify additional mechanisms.
