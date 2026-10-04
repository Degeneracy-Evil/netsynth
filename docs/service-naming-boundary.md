# Service Naming and Discovery Boundary

> Status: architecture boundary decision.
>
> This is not a new routing Scale. NetSynth deliberately does not define one mandatory global human/service naming system.

## 1. Problem

The frozen architecture begins network delivery from an Endpoint ID:

~~~text
EID
  -> Endpoint Binding
  -> LocatorSet
  -> selected Locator
  -> Route Program
~~~

Real applications often begin with a human/application concept such as:

~~~text
"the object store"
"chat service"
"printer in this room"
"api.example"
~~~

The question is whether NetSynth should make those names part of the network architecture.

## 2. Prior-art reconciliation

### DNS

DNS demonstrates that a hierarchical namespace can scale through administrative delegation, authoritative zones and caching.

Its hierarchy is valuable for global organizational ownership, but that governance structure is not a property of packet forwarding.

### SRV / SVCB / DNS-SD

Modern DNS service mechanisms already separate a logical service name from one physical destination.

A service lookup may return:
- multiple alternatives;
- priority/weight;
- protocol/application parameters;
- named service instances.

The important lesson is:

> service discovery should normally return a set of candidate service endpoints, not one hard-coded network location.

### SDSI

SDSI demonstrates that useful naming need not require one global hierarchical namespace. Names can be local to principals and linked between namespaces.

Thus a single global human-readable naming hierarchy is not forced by networking fundamentals.

### Named Data Networking

NDN takes the stronger architectural choice of putting names into forwarding itself.

Routers maintain name-based forwarding/pending state and packets are routed toward named data.

NetSynth does not choose this path. The frozen Locator/Scope/Route-Program design intentionally keeps transit forwarding independent of human/service/content naming.

## 3. Architecture choice: naming remains above Endpoint identity

A naming/discovery system may resolve an application Service Reference into one or more Endpoint candidates:

~~~text
Service Reference
      |
      v
Service Resolution
      |
      v
{ Endpoint ID candidates + service metadata }
      |
      v
Endpoint Binding Service
      |
      v
LocatorSet
~~~

Service names never enter Scale-4 transit routing.

## 4. Service resolution result

The common boundary is conceptually:

~~~text
ServiceResolution {
    candidate EIDs
    application/protocol profile
    optional preference / weight
    validity / freshness metadata
}
~~~

Exact fields are not frozen.

The important invariant is:

> endpoint candidates are expressed as EIDs, never as routing Locators.

A naming system may also return additional application-layer metadata needed before Channel establishment.

## 5. Multiple EIDs are normal

A logical service may have several concrete Endpoint identities:

~~~text
service
    -> {EID_A, EID_B, EID_C}
~~~

This covers:
- replicated services;
- regional instances;
- blue/green deployments;
- rolling upgrades;
- different protocol capabilities.

Selection among service instances occurs before normal EID-to-Locator resolution.

This is distinct from one EID having several Locators:

~~~text
service replication:
    Service -> many EIDs

Endpoint multihoming:
    one EID -> many Locators
~~~

Do not conflate them.

## 6. No transport ports reintroduced

A service discovery result identifies an Endpoint/application profile.

It does not require NetSynth to reintroduce a global numeric port namespace.

If an Endpoint intentionally hosts several application protocols, the service-resolution metadata or the application-level Channel establishment protocol can distinguish them.

Do not turn service discovery into a disguised TCP port registry.

## 7. Naming trust is separate from EID trust

The Security Floor proves:

> the Channel peer controls EID X.

It does **not** prove:

> EID X is the service the user intended.

Therefore a naming system that makes trusted service-name claims needs its own authority/trust semantics.

Examples may include:
- DNS/DNSSEC-like organizational delegation;
- locally configured names;
- SDSI-like principal-relative names;
- application-managed directories.

NetSynth does not freeze one governance system.

Once a naming layer returns EID X, the frozen Security Floor independently verifies that the contacted peer actually controls X.

## 8. Why there is no NetSynth global name root

A global service-name root would create policy/governance commitments unrelated to the forwarding architecture:

- who owns names;
- dispute resolution;
- internationalization;
- organizational delegation;
- censorship/policy;
- human identity.

No current NetSynth mechanism requires one universal answer.

Therefore the common network architecture stops at self-certifying EIDs.

## 9. Caching and change

Service-resolution results may be cached independently of Endpoint Bindings.

This creates another explicit lifetime boundary:

~~~text
Service -> EID set             deployment/service lifetime
EID -> LocatorSet              mobility lifetime
Locator -> Route Program       routing/cache lifetime
~~~

Changing one service replica does not require changing another Endpoint's identity or routing topology.

## 10. Local discovery

Local/ad-hoc service discovery may use multicast, a local directory, configuration, or another mechanism.

That is a later question if NetSynth derives a common local-discovery/multicast facility.

It is not a reason to add broadcast semantics to the core now.

## 11. Result

The end-to-end lookup chain becomes:

~~~text
optional Service Reference
        |
        v
service naming/discovery layer
        |
        v
candidate EID(s)
        |
        v
Endpoint Binding
        |
        v
Locator(s)
        |
        v
Route Program
        |
        v
authenticated Channel
~~~

Only the lower four stages are required by the NetSynth common network architecture.

## 12. No semantic prototype required

There is nothing NetSynth-specific to validate at this boundary yet.

A mock string-to-EID dictionary would merely prove that dictionaries work.

Do not add a naming simulator or DNS replacement.

The next architecture work should return to an unresolved property of the network substrate itself.
