# Naming, Resolution, and Routing Reconciliation

> Status: architecture derivation in progress. This revises earlier claims that Endpoint-ID / Locator separation is mathematically mandatory.

## 1. Corrected principle

General weighted graphs admit compact name-independent routing directly on arbitrary topology-independent names. Therefore explicit Endpoint-ID / Locator separation is not logically mandatory.

The correct statement is:

> Routing information associated with a topology-independent destination must live somewhere: distributed routing state, a directory, a topology-dependent descriptor, packet header state, session state, or a combination.

The information does not disappear when namespaces are merged or separated.

## 2. Three integration modes

### A. Inline name-independent routing

~~~text
stable Endpoint ID
        |
        v
name-independent routing / distributed lookup
        |
        v
destination
~~~

The routing system absorbs the name-to-topology problem.

### B. Explicit resolution + labeled routing

~~~text
Endpoint ID
    |
    | resolve
    v
Routing Descriptor
    |
    v
name-dependent compact routing
~~~

This can reduce hot-path routing cost but creates resolver state, lookup cost and descriptor churn.

### C. Resolution + session handshake

~~~text
Endpoint ID
    |
    v
Routing Descriptor
    |
    | first contact / handshake
    v
Session Routing Context
    |
    v
subsequent packets
~~~

This allows peer-specific routing information to be learned once and amortized.

## 3. Name-independent routing as in-path resolution

Classic name-independent constructions often use a distributed dictionary. A packet begins with only the stable arbitrary name, reaches a node holding corresponding topology-dependent contact/routing information, then continues toward the target.

Explicit Rendezvous moves this lookup before ordinary data forwarding and may cache the result.

The real design axis is therefore lookup placement and cache lifetime, not whether mapping information exists.

## 4. UIA is direct prior architecture

Bryan Ford's UIA work already explored a closely related composition:
- persistent topology-independent endpoint identities;
- name-dependent Thorup-Zwick-derived compact routing;
- topology-sensitive global addresses/locators;
- DHT/directory resolution;
- conversation reuse;
- cooperative/handshake route improvement.

UIA explicitly argued that a single address lookup can be preferable to repeatedly paying the path penalty of name-independent routing when peers exchange multiple messages.

NetSynth must treat this as direct prior art. Future claims must state how a design differs from or updates UIA.

## 5. Endpoint namespace and forwarding graph are separate axes

Let:
- F be forwarding nodes / routing anchors;
- H be communicating endpoints;
- A subset H x F be the attachment relation.

An Endpoint does not have to be a vertex participating in global forwarding.

A Routing Descriptor may identify one or more attachment forwarding nodes using the active routing scheme, plus local-delivery information.

This can make global routing structure scale primarily with |F| while the Endpoint namespace may be much larger.

Endpoint movement can then change A without necessarily changing the forwarding graph.

## 6. Attachment information lower bound

With E endpoints and R possible single-homing forwarding anchors, there are R^E possible exact attachment assignments.

Any exact global representation capable of distinguishing all assignments requires at least:

~~~text
log2(R^E) = E log2 R
~~~

bits in aggregate, absent exploitable correlation.

This unavoidable information may live in:
- name-independent routing/dictionaries;
- an explicit sharded resolver;
- endpoint/anchor state plus discovery;
- caches.

The architecture objective is to avoid replicating endpoint-scale information at every forwarder.

## 7. Rendezvous becomes a function, not a mandatory layer

Logical contract:

~~~text
resolve(EndpointID) -> current Routing Descriptor Set
~~~

Possible implementations include an explicit DHT/directory, locality-aware resolution, peer caches, or an in-path name-independent lookup mechanism.

## 8. Routing Descriptor generalizes Structured Locator

A Routing Descriptor is scheme-defined topology-dependent contact information. It may be:
- the historical Structured Locator;
- a compact-routing node label;
- landmark/tree-cover labels;
- attachment-anchor labels;
- multiple alternatives for multihoming;
- local final-delivery information.

The packet need not carry the whole descriptor verbatim.

## 9. Channel as a routing-context lifetime

A Channel may cache:
- resolution results;
- selected landmark/tree;
- handshake-derived routing state;
- alternative descriptors;
- generation/version information.

One-shot communication must remain possible without persistent Channel state.

## 10. Dynamics trade one maintenance problem for another

Topology-dependent descriptors may change as attachments or routing structures change. Name-independent routing keeps the stable external name but must update internal routing/dictionary state.

Thus the dynamic comparison is:

~~~text
descriptor churn + resolver update + cache invalidation
versus
name-independent routing/dictionary maintenance
~~~

This requires reconciliation with dynamic compact-routing and dynamic labeling theory.

## 11. Historical claims to revise

Too strong:
> Endpoint ID and Locator must be separate.

Revised:
> Stable topology-independent naming and topology-dependent routing create an information-placement trade-off. NetSynth should support both direct name-independent routing and explicit resolution to labeled routing.

Too strong:
> Independent movement creates a Rendezvous-layer lower bound.

Revised:
> Independent movement creates an attachment-information requirement. Explicit Rendezvous is one realization; name-independent distributed routing/dictionaries are another.

Still useful:
- endpoint-scale information should not be globally replicated by default;
- long-lived communication may amortize resolution/setup;
- routing-state and endpoint-mapping state must be measured separately;
- topology change should ideally have locality-sensitive maintenance.

## 12. Simulator consequence

The future model should distinguish:

~~~text
ForwardingGraph
EndpointSet
AttachmentRelation
EndpointNamingModel
ResolutionStrategy
RoutingScheme
SessionStrategy
PacketRoutingHeader
~~~

The historical simulator conflates several of these. Do not refactor until this model and the compact-routing resource model are accepted together.
