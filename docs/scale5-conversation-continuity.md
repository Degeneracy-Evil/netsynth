# Scale 5: Ongoing Communication Across Mobility

> Status: architecture choice.
>
> Question:
>
> Once stable EIDs and EID-to-LocatorSet resolution exist, does mobility force NetSynth to add a generic Channel/session protocol?

## 1. Prior-art reconciliation

### HIP

HIP binds transport associations to stable Host Identities rather than IP locators. Locator changes therefore do not redefine the peer identity.

### QUIC

QUIC uses endpoint-chosen Connection IDs so a transport connection survives changes in lower-layer address/port tuples. Path migration then validates the new path and resets or adapts path-dependent transport state.

### MPTCP / SCTP

MPTCP joins multiple address-pair subflows into one connection using connection-level identity/keying. SCTP associations may contain multiple peer transport addresses and dynamically change address sets.

### MobilityFirst msocket

MobilityFirst's endpoint socket library combines identity/location resolution with persistent connections, multihoming and multipath.

The common lesson is:

> conversation state must not be keyed only by the current network locator.

It does **not** imply that the network layer must define one universal session protocol.

## 2. Architecture choice: no generic Channel yet

Scale 5 does **not** introduce a mandatory NetSynth Channel ID or network-resident session object.

Mobility requires only this cross-layer contract:

> any upper-layer state that intends to survive movement must bind its peer identity to the stable EID, not to the current Locator or Route Program.

Locator and Route Program are replaceable delivery state.

A future transport may introduce its own connection/session identifier when multiplexing, reliability, ordering, privacy, or migration semantics force one.

## 3. Endpoint-side communication state

An ongoing upper-layer association conceptually keeps:

```text
Remote EID
cached BindingVersion / LocatorSet
selected Locator(s)
cached Route Program(s)
upper-layer protocol state
```

Only the first and last items are semantically part of the conversation.

Binding, Locator and Route Program are cached delivery material and may be replaced.

## 4. Mobility recovery

When delivery state becomes stale:

```text
upper-layer association remains
        |
        v
networking edge detects route/attachment failure
        |
        +-- recompile Scale-4 route to same Locator when useful
        |
        +-- try another Locator from same binding
        |
        +-- fresh-resolve Remote EID
                |
                v
             new Locator
                |
                v
         new Route Program
                |
                v
upper-layer association continues
```

Whether data is retransmitted, reordered, or congestion state is reset belongs to the later transport design.

## 5. No mandatory direct peer mobility update

HIP demonstrates that direct peer locator updates can reduce mobility interruption.

NetSynth does not require such updates for Scale-5 correctness.

The Binding Service remains the rendezvous fallback, including simultaneous movement.

A future transport or endpoint-control protocol may send direct binding hints to active peers as an optimization.

Such hints must not become the only way to recover current location.

## 6. No mandatory per-flow state in the network

The Scale-4 forwarding substrate remains unchanged.

Transit nodes do not learn:
- EID-to-Locator bindings;
- connection IDs;
- per-conversation state.

Mobility/session continuity is an endpoint/edge concern.

## 7. Packet implication

Scale-5 network delivery still uses:

```text
Destination EID
Selected Destination Locator
Hop Budget
Route / Transit Stack
Payload
```

No generic Channel ID is added.

A later transport header may add a transport-specific connection identifier above this network envelope.

Likewise, Scale 5 does not add a mandatory Source EID field to every network packet. A protocol that requires stable sender identity can carry or establish that information at its own layer.

## 8. Path-dependent state must be separable

QUIC migration highlights an important future transport rule: RTT, congestion, PMTU and validation state belong to a path, not to endpoint identity.

NetSynth records this as an architecture constraint:

```text
peer identity state != path state
```

When a Locator/Route Program changes, path-dependent transport state may need to be revalidated or reset without destroying the peer association.

The transport phase must honor this separation.

## 9. What Scale 5 has now achieved

Scale 5 can support:

- stable endpoint references;
- attachment movement;
- multihoming;
- new communication after movement;
- recovery of ongoing upper-layer communication by re-resolving the same EID;
- simultaneous mobility through rendezvous fallback;

without:
- changing Scale-4 transit forwarding;
- a global EID FIB;
- permanent forwarding pointers;
- a mandatory network Channel/session layer.

## 10. When Channel should be reconsidered

Introduce a common Channel only if a later architecture question shows that multiple transports/applications repeatedly need the same standardized state, such as:

- common connection demultiplexing independent of Endpoint ID;
- standardized path validation/migration signaling;
- shared multipath selection;
- shared security association;
- common reliability/congestion semantics.

Until then, Channel remains a historical candidate, not a frozen NetSynth primitive.
