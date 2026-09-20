# Routing Object Model v2

> Status: theory-level candidate for the future NetSynth simulator. No implementation is authorized yet.

## 1. Separate the forwarding substrate from communication endpoints

Let the forwarding substrate at time t be a weighted port graph:

~~~text
F_t = (V_F, E_F, w, ports)
~~~

where V_F contains entities participating in global/multi-hop forwarding.

Let:

~~~text
H = set of stable communication Endpoints
~~~

and let the time-varying attachment relation be:

~~~text
A_t subset H x (V_F x LocalSelector)
~~~

An Endpoint may attach to one or multiple forwarding anchors. A physical machine may simultaneously host Endpoints and act as a forwarding vertex; these are roles, not disjoint device classes.

The final LocalSelector is meaningful only at the selected attachment anchor. Its semantics are not part of the global routing scheme.

## 2. Classical compact routing is a special case

The standard compact-routing model is recovered by:

~~~text
H = V_F
A(v) = {(v, local-self)}
~~~

and by using the node name or routing label of v directly as the destination information.

Thus the v2 object model strictly generalizes the theory model rather than replacing it.

## 3. Endpoint-to-anchor mapping is independent of core routing

For an Endpoint h, the system must eventually determine one or more reachable attachment anchors.

Conceptually:

~~~text
EndpointID(h)
    -> Attachment Descriptor Set
    -> anchor routing information + local selector
~~~

How that mapping is obtained is a separate design axis:

- explicit pre-send resolution;
- distributed in-path lookup;
- local/shared cache;
- peer-provided information;
- session handshake;
- another theory-backed mechanism.

Name-independent routing can therefore be represented without adding Endpoints as vertices: the stable Endpoint ID is a dictionary key whose value contains routing information for an attachment anchor.

## 4. Generic destination model

Do not assume every packet carries a Structured Locator.

Define three distinct objects:

### Stable Endpoint ID

Application/session-facing identity with topology-independent lifetime semantics.

### Routing Descriptor

Scheme-defined topology-dependent information sufficient to initiate routing toward one attachment.

Examples:
- historical Structured Locator;
- compact-routing label of an anchor;
- landmark/tree-cover label tuple;
- any other scheme-defined descriptor.

### Packet Routing Header

The actual on-wire, potentially mutable state consumed by the routing scheme.

A scheme may:
- put the descriptor directly in the header;
- transform it into a smaller header;
- retrieve additional information in-path;
- combine it with Session Routing Context.

## 5. Orthogonal strategy axes

A complete NetSynth routing experiment should compose independent choices.

### Endpoint naming model
How stable Endpoint IDs are formed. Security semantics remain out of scope for now.

### Attachment / resolution strategy
How Endpoint ID maps to current attachment descriptors.

### Core routing scheme
How packets route between forwarding vertices.

### Session strategy
Whether first contact establishes reusable routing context.

### Local delivery strategy
How the chosen anchor reaches the local Endpoint. Initially this may be modeled as zero-cost delivery or an explicit local link, but it must not leak into global routing state silently.

### Port model
Fixed/adversarial, designer-controlled, or logical-port mapping with charged translation state.

## 6. Generic execution pipeline

One-shot explicit-resolution mode:

~~~text
EndpointID
    |
 resolve()
    v
Routing Descriptor
    |
 initialize_header()
    v
packet header
    |
 route_step() repeatedly over F
    v
attachment anchor
    |
local delivery
    v
Endpoint
~~~

Name-independent/in-path mode:

~~~text
EndpointID in packet/input
    |
routing + distributed lookup over F
    |
possibly rewritten header containing acquired routing info
    |
attachment anchor
    |
local delivery
~~~

Session mode:

~~~text
EndpointID
  -> resolution
  -> optional handshake
  -> Session Routing Context
  -> many packet headers/routes
~~~

These are resource-placement choices, not separate notions of reachability.

## 7. Multihoming

A_t(h) may contain multiple anchors.

Do not invent selection semantics yet.

Future work must reconcile with anycast/multihoming routing theory before deciding whether:
- the resolver chooses one anchor;
- the source chooses from descriptors;
- the routing scheme performs anycast;
- a Channel keeps multiple live alternatives.

The object model only needs to permit a descriptor set.

## 8. Mobility and change domains

Distinguish at least:

### Forwarding-topology change
Changes F_t.

### Endpoint attachment change
Changes A_t while F_t may remain unchanged.

### Routing-scheme relabeling
Changes topology-dependent labels/descriptors even if endpoint attachment is unchanged.

### Resolution/cache change
Updates the mapping material exposed to sources/sessions.

These events can have very different propagation costs and must not be collapsed into one generic "routing churn".

## 9. Information requirement

For E independent single-homed Endpoints and R possible attachment anchors, an arbitrary exact attachment assignment has R^E possibilities and therefore requires E log2 R bits in aggregate to distinguish in the worst case.

This is only a counting lower bound under arbitrary independent assignments; real attachment structure may compress.

The architectural question is where this unavoidable information is stored and replicated, not whether it can be removed.

## 10. Relationship to prior architectures

This object decomposition has substantial prior architectural precedent.

- LISP explicitly separates Endpoint Identifiers from Routing Locators and stores EID-to-RLOC bindings in a Mapping System; the core routes on RLOCs.
- HIP introduces a host-identity namespace distinct from IP locators and uses a protocol layer between transport and internetworking.
- ILNP explicitly separates non-topological node Identifiers from topologically bound Locators.
- UIA explored stable EIDs, routing/location discovery, and in its thesis a compact-routing design using topology-sensitive locators plus lookup/conversation reuse.

NetSynth must therefore treat identity/locator separation and mapping systems as established architectural design space, not as a new contribution.

## 11. What may still be NetSynth-specific

The candidate research question is narrower:

Can one common architecture expose naming, resolution, session state, and routing as composable resource-bearing interfaces, then select theory-backed routing constructions per forwarding-graph family while preserving explicit ownership, dynamic locality, and physical hop-by-hop realizability?

This is an integration/operational-semantics question, not a new identifier/locator theorem.

## 12. Simulator consequence

The next simulator should represent independently:

~~~text
ForwardingGraph
EndpointSet
AttachmentRelation
PortModel
RoutingScheme
ResolutionStrategy
SessionStrategy
ResourceCostModel
~~~

Historical Phase 1-5 experiments should map to the degenerate classical case H=V_F with no separate attachment lookup.
