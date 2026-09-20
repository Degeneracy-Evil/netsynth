# Scale 4 Transit Context

> Status: architecture choice following the Scoped Transit Pathlet contract.
>
> This document answers:
>
> How does a packet invoke recursively composed Scoped Transit Pathlets without per-flow router state or a source-selected end-to-end route?

## 1. Problem forced by the summary contract

A parent may select a child Scoped Transit Pathlet (STP) as an abstract routing action.

The final Destination Locator alone cannot generally tell the child which boundary-to-boundary transit service the parent selected.

Therefore some additional routing information must exist during pathlet realization.

Possible locations are:
- per-flow state in the forwarding network;
- an end-to-end source route in the packet;
- temporary packet-carried transit context.

NetSynth chooses the third.

## 2. Prior-art reconciliation

### MPLS

MPLS already provides the fundamental data-plane mechanism NetSynth needs:
- a label stack;
- top-label forwarding;
- label swap;
- push for nested tunnels;
- pop when a tunnel/path completes.

NetSynth reuses this mature mechanism rather than inventing a new stack machine.

It does **not** inherit MPLS FEC semantics, signaling protocols, VPN semantics, or compatibility constraints.

### Segment Routing

Segment Routing encodes an ordered list of instructions/segments at a headend and is explicitly based on source-routing semantics.

NetSynth does not choose this as the default Scale-4 model.

The source does not need to know or encode the end-to-end path.

### Pathlet Routing

Pathlet Routing uses path fragments and forwarding identifiers that may themselves invoke lower-level pathlets.

This is very close to NetSynth STP realization.

The major NetSynth choice is that pathlet selection remains network-driven by the final Destination Locator rather than requiring the source to concatenate an end-to-end pathlet route.

## 3. Architecture choice: Transit Stack

The Scale-4 transit unit becomes conceptually:

~~~text
TransitUnit {
    Destination Locator
    Hop Budget
    Transit Stack
    Payload
}
~~~

The Transit Stack is normally empty.

It exists only while the network is realizing one or more abstract routing actions.

## 4. Two forwarding modes

### Destination mode

When Transit Stack is empty:

~~~text
Destination Locator -> ordinary routing decision
~~~

The node may:
- forward directly over a physical link;
- enter the destination's finer routing resolution;
- invoke an advertised STP.

### Transit mode

When Transit Stack is non-empty:

~~~text
top Transit Label -> label-switching decision
~~~

The final Destination Locator is not used to choose the immediate transit action.

The label lookup may:
- forward over a physical link;
- replace/swap the top label;
- push a lower-level label;
- pop the completed label.

When the stack becomes empty, ordinary Destination-Locator forwarding resumes.

## 5. Labels are routing-local, not identities

A Transit Label is:
- opaque;
- short-lived relative to Endpoint identity;
- meaningful only to the routing/control context that allocated it;
- not globally unique by architectural requirement;
- not an address;
- not a destination name.

A label exists only to realize an already-advertised routing object.

This keeps the common forwarding instruction small and semantically poor.

## 6. Recursive pathlet realization

Suppose Scope S exports parent pathlet X.

Its internal realization may contain a child pathlet Y.

Conceptually:

~~~text
stack before child:
    [ X ]

invoke child Y:
    [ X, Y ]

while Y active:
    top(Y) drives forwarding

Y completes:
    [ X ]

X resumes

X completes:
    [ ]
~~~

The implementation may use label swapping so that the continuation label exposed after a pop is already the value expected at the downstream continuation point, exactly as nested label switching systems do.

The architecture does not require a globally meaningful pathlet identifier.

## 7. Stack-depth bound

Because Scope membership is laminar and an STP realization can delegate only to routing objects in proper descendant Scopes, nested invocation depth is bounded by Scope hierarchy depth.

Sequential pathlets at the same level are pushed and popped rather than accumulated.

Therefore the packet does not carry a path-length-sized source route.

This is a key difference from an arbitrary end-to-end segment list.

## 8. No mandatory per-flow state in forwarding nodes

Transit labels identify reusable pathlet forwarding state, not an individual flow.

Many packets may invoke the same STP.

The Scale-4 common forwarding core therefore does not require network-resident per-flow routing state.

Per-flow/session mechanisms may appear later for other reasons, but they are not required to realize Scope summaries.

## 9. Local repair semantics

A label identifies the STP service, not one immutable physical path.

A Scope may change:
- which physical links realize the pathlet;
- lower-level labels used internally;
- local next-hop choices;

without changing the parent-visible STP or packet-visible invocation label, as long as the advertised contract remains valid.

This preserves the Scale-4 change-containment goal.

## 10. Packet overhead is now an explicit architecture cost

Theory reconciliation previously showed that writable packet state is a legitimate routing resource.

NetSynth now introduces it for a concrete architecture reason.

The relevant cost is no longer an arbitrary generic header budget.

It is specifically:

~~~text
maximum nested Transit Stack depth
x
per-level Transit Label width
~~~

plus minimal stack framing/operation semantics.

Exact wire encoding is postponed.

## 11. Failure semantics

If an active Transit Label can no longer be realized:
- the Scope should first attempt local repair;
- if repair is impossible, the active transit operation fails explicitly;
- a stale/invalid Transit Label must not silently be reinterpreted as an unrelated label or as ordinary destination forwarding.

Hop Budget remains a final bound on inconsistent forwarding behavior.

Generation/reuse rules for labels belong to the later dynamic-control design.

## 12. What NetSynth is not adopting

This design does not imply:
- MPLS protocol compatibility;
- LDP/RSVP;
- global source routing;
- Segment Routing policies;
- source-selected pathlet sequences;
- network-resident per-flow LSP state;
- administrative AS semantics.

Only the push/swap/pop label-stack mechanism is adopted as the clean solution to recursive transit realization.

## 13. Resulting Scale-4 data-plane model

Conceptually:

~~~text
if TransitStack.nonempty:
    execute top transit label
else:
    route toward Destination Locator

always:
    decrement / enforce Hop Budget
~~~

This remains a small fast-path model.

The complexity is moved into the control plane that creates Destination routing state and reusable pathlet labels.

## 14. Next architecture question

The remaining Scale-4 routing question is now the central one:

> Given Structured Locators, child Boundary Transit Graphs, crossing links, and the ability to execute STPs, how does a node choose the next physical link or STP toward a destination without restoring flat global state?

This is where compact-routing / hierarchical-routing mathematics should directly constrain the NetSynth routing-control algorithm.

The next step must compare candidate mathematical constructions against NetSynth's explicit architecture priorities before choosing one.
