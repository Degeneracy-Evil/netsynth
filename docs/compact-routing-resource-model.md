# Compact-Routing Resource Model for NetSynth

> Status: theory contract for the next simulator architecture. This does not authorize implementation.

## 1. Standard routing model

For a weighted forwarding graph G=(V,E,w), preprocessing may produce:
- a routing label for each vertex;
- persistent local routing information;
- optional scheme-defined logical port assignments;
- optional public/global parameters.

A forwarding step is modeled as:

~~~text
route_step(
    current_node,
    incoming_port?,
    destination_information,
    mutable_header,
    local_table
) -> (
    outgoing_physical_port | delivered | failure,
    updated_header
)
~~~

This model must support name-dependent, name-independent, fixed-header, writable-header, and handshake/session schemes.

## 2. Name model

In name-dependent/labeled routing, preprocessing may assign topology-dependent labels and the source is normally assumed to know the destination label before forwarding begins. The cost of acquiring that label is usually outside the static compact-routing theorem.

In name-independent routing, the packet starts with an externally assigned topology-independent name. Any directory/lookup information needed to route that name is therefore part of the routing system itself.

NetSynth must not compare these models without charging destination-label acquisition for the labeled scheme.

## 3. Port numbering is a resource

Record whether a scheme assumes fixed/adversarial ports or designer ports.

Designer-port numbering can encode topology information. If NetSynth permits scheme-defined logical port numbering, either:
1. the architecture explicitly grants control over physical local interface numbering; or
2. a logical-to-physical port map is charged as persistent state and update churn.

Port numbering must never become hidden free routing memory.

## 4. Static resource vector

Replace normalized scalar size as the primary cross-scheme metric.

Record separately:

### Destination / label state
- max and average routing-label bits;
- Endpoint-ID bits when relevant;
- routing-descriptor bits returned by resolution.

### Router-local persistent state
- max / average / total routing-table bits;
- logical-port mapping bits;
- additional persistent routing-control bits.

### Packet state
- destination-information bits carried on wire;
- initial routing-header bits;
- maximum mutable-header bits;
- maximum total packet routing metadata bits.

### Session state
- source endpoint routing-context bits;
- destination endpoint routing-context bits;
- network-resident per-session state, if any.

Do not merge label, table, header and session state into one scalar.

## 5. Resolution resource vector

For explicit Endpoint-ID -> Routing-Descriptor resolution, record:
- total and per-node directory state;
- lookup messages and bytes;
- critical-path lookup cost;
- total network work of the lookup;
- descriptor update traffic;
- cache invalidation / lease / generation churn when modeled.

For name-independent schemes the external resolution cost is zero, but any internal distributed dictionary belongs in routing/control state.

## 6. Session / handshake vector

For handshake-based routing or a NetSynth Channel that caches routing context, record:
- handshake message count and bytes;
- handshake roundtrip stretch/latency;
- resulting cached context bits;
- steady-state data-route stretch;
- invalidation rate under dynamics.

For m data messages, compare schemes with:

~~~text
C(m) = C_resolution + C_setup + m * C_data
~~~

Report critical-path communication cost and total network work separately.

## 7. Performance vector

Record:
- worst-case and empirical weighted stretch;
- hop stretch;
- exact-shortest fraction;
- route failures;
- loops / Hop-Budget exhaustion when dynamics are modeled;
- per-hop decision cost where meaningful.

When a theorem provides a guarantee, output the theorem guarantee separately from measured instance behavior.

## 8. Construction model

Every scheme must declare whether construction is:
- centralized/global-map;
- sequential;
- distributed LOCAL/CONGEST-like;
- deterministic or randomized.

Record construction rounds/messages/bytes or centralized work as appropriate. A centralized theoretical construction must not be presented as a deployable control plane.

## 9. Dynamic resource vector

When topology changes are studied, record separately:
- changed table bits;
- changed routing-label bits;
- changed port-map bits;
- changed resolver records;
- invalidated session contexts;
- update messages/bytes/rounds;
- convergence latency;
- transient forwarding failures/loops.

Dynamic experiments require theory reconciliation first.

## 10. Theory metadata

Every routing implementation should eventually expose:
- citations;
- graph/weight assumptions;
- name model;
- port model;
- randomization model;
- table/label/header guarantees;
- stretch guarantee;
- handshake guarantee;
- construction model;
- fault/dynamic assumptions;
- implementation fidelity and deviations.

## 11. Bit-cost modes

Support both:
- a theory-normalized model, e.g. references parameterized by log n / degree / weight precision;
- a concrete architecture model with explicitly configured widths.

Do not bake current Internet widths into the mathematical core.

## 12. Initial theory registry

Before new mechanisms, reconcile at least:
- Flat exact routing;
- exact compact tree routing / routing labeling;
- Cowen/Thorup-Zwick labeled stretch-3 routing;
- parameterized Thorup-Zwick-style handshake routing;
- minimum-stretch name-independent compact routing for general weighted graphs;
- at least one specialized low-doubling-dimension routing scheme.

The future simulator must not force these constructions through ScopeTree or summary.usable_edges().
