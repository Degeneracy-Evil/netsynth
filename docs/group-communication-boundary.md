# Group Communication Boundary

> Status: architecture boundary decision.
>
> NetSynth does not add a mandatory network-wide group/multicast transport primitive at this stage.

## 1. Problem

The frozen common architecture is point-to-point:

~~~text
Endpoint -> Endpoint
~~~

Many real workloads are one-to-many or many-to-many:
- replicated services;
- publish/subscribe;
- software/data distribution;
- conferencing;
- HPC / AI collectives.

The question is whether efficient replication must become a first-class common network semantic.

## 2. Prior-art reconciliation

### IP multicast / SSM

IP multicast defines a network-layer host-group delivery abstraction. Source-Specific Multicast narrows this to one-to-many delivery from a known source.

This can avoid sending the same packet independently over shared links, but introduces multicast membership/routing machinery and a separate group-address namespace.

### End System Multicast

Application/end-system multicast demonstrates that group dissemination can be implemented entirely above unicast by building an overlay tree among endpoints.

Its main cost is path/bandwidth inefficiency relative to ideal router replication.

Therefore network multicast is an optimization opportunity, not a prerequisite for group-communication correctness.

### BIER

BIER demonstrates an especially relevant modern compromise:

- ingress knows the set of egress routers;
- the destination set is carried in the packet;
- transit nodes replicate as needed;
- no per-flow/per-group multicast state is required in the core.

This is philosophically compatible with NetSynth's existing preference for packet-carried route state and reusable destination-independent forwarding state.

BIER therefore remains strong prior art if NetSynth later adds a replication accelerator.

### Reliable multicast

Reliable multicast work such as PGM shows that group reliability is substantially more complicated than unicast reliability:

- ACK/NAK implosion;
- repair localization;
- receiver heterogeneity;
- membership and loss-recovery interaction.

Network replication alone does not solve these transport semantics.

### HPC / AI collectives

Systems such as SHARP show that specialized in-network replication **and aggregation/reduction** can provide major performance gains for tightly controlled HPC/AI fabrics.

But reduction is application/operation-specific in-network computing, not a generally required Internet/network-core semantic.

## 3. Security/transport constraint from frozen NetSynth

Scale 6 Channels are pairwise objects with receiver-specific:

- Receive Tokens;
- Packet Numbers / ACK state;
- flow control;
- congestion/path state;
- traffic keys.

The Security Floor provides pairwise Channel AEAD.

Therefore this is invalid:

~~~text
one pairwise Channel ciphertext
        |
        +-- network copies to B
        +-- network copies to C
        +-- network copies to D
~~~

B/C/D do not share one Channel identity/key/state.

Thus "router can replicate bits" and "reliable secure group communication" are different architecture questions.

## 4. Architecture choice: point-to-point remains the common semantic floor

NetSynth does **not** introduce into the common architecture:

- Group ID / multicast address;
- router-maintained group membership;
- multicast distribution-tree state;
- reliable group Channel;
- group ACK/NAK protocol;
- group key management;
- collective reduction operation.

Applications can always implement group semantics over ordinary Channels.

This is the universal correctness fallback.

## 5. Overlay group communication is the baseline

A group library may build an overlay dissemination tree:

~~~text
A
|\
B C
  |\
  D E
~~~

Each edge is an ordinary authenticated NetSynth Channel.

This preserves all frozen:
- EID identity;
- mobility;
- reliability;
- congestion control;
- security.

Overlay topology and membership remain application/library state.

## 6. Optional replication acceleration is not ruled out

BIER shows that an underlay can replicate one opaque group packet to a known set of egress positions without persistent per-group core state.

NetSynth may later define an **optional scoped replication capability** if measurements show that overlay duplication wastes enough bandwidth to justify it.

If introduced, it should obey these constraints:

- no globally replicated group membership in transit routers;
- destination/branch information is packet- or setup-carried;
- replication remains Scope/locality-aware;
- it is best-effort delivery acceleration, not group reliability;
- group membership/security remains above it;
- ordinary unicast Channels remain the fallback.

Do not add this capability merely because forwarding hardware can clone packets.

## 7. Why BIER is not adopted immediately

A BIER-like primitive still forces unresolved choices:

- how group payload is locally demultiplexed at different egresses;
- how destination sets are encoded when large;
- how it composes with hierarchical Route Programs;
- whether the payload uses a shared group-security context;
- how congestion feedback is attributed to many receivers.

None of these are necessary for point-to-point correctness.

The architecture therefore waits for a concrete workload/performance requirement.

## 8. HPC / AI profile

Collectives deserve a future **deployment/profile capability**, not common-core semantics.

A datacenter/HPC profile may expose capabilities such as:

~~~text
replicate
reduce(op)
aggregate
collective-tree offload
~~~

when switches/NICs support them.

SHARP is direct evidence that this can be extremely valuable.

However, a general-purpose NetSynth deployment must remain correct without any such in-network compute.

## 9. Result

The common architecture remains:

~~~text
Endpoint <-> Endpoint Channel
~~~

Group communication is layered above it.

Efficient in-network replication/reduction is an optional acceleration direction, not currently a frozen primitive.

## 10. No semantic prototype required

An overlay tree built from Channels would only re-demonstrate that point-to-point links can compose.

A BIER-like accelerator would require an actual performance/use-case justification before its extra semantics are worth validating.

Do not build a group simulator now.
