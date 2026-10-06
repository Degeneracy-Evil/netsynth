# NetSynth v0.1 Realization and Benchmark Plan

> Status: post-v0.1 realization design.
>
> Goal: turn the frozen semantic architecture into a real packet-processing system and determine whether its architectural structure creates measurable value over strong modern baselines.
>
> Compatibility with IP/TCP/UDP/MPLS/SRv6 is not a requirement for the NetSynth implementation.

## 1. What must be proved

The project should not attempt to prove that NetSynth is universally faster than TCP/IP.

The first implementation must answer three narrower questions.

### A. Is the steady-state cost acceptable?

On a stable path, NetSynth must expose the real cost of custom packet headers, route-code parsing, local token lookups, Channel/security processing, and packet I/O.

Steady-state throughput and latency are guardrails. A clean architecture that is unusably expensive has no practical value.

### B. Does Scope containment create measurable operational value?

When a failure can be repaired inside one Scope while its hard STP contract remains valid, measure whether NetSynth avoids parent routing updates, ingress route recompilation, and broad control-plane churn.

Modern IP already has local fast-reroute mechanisms. The claim is therefore not merely that NetSynth can reroute quickly.

The stronger claim is:

> a local physical repair can remain a purely owner-local implementation change indefinitely while the parent-visible transit contract remains valid.

### C. Does identity/location separation create measurable endpoint-mobility value?

When an Endpoint changes attachment:

~~~text
EID stays stable
Binding changes
Locator / Path State changes
Channel survives
~~~

Measure whether this is simpler or less disruptive than modern address-bound systems.

This must be tested against QUIC and MPTCP, not only traditional TCP.

## 2. Strong baselines

### Transport baselines

Use:

1. Linux TCP + CUBIC as the production-grade bulk-transfer baseline.
2. MsQuic / QUIC as the modern encrypted migration/multi-stream baseline. SecNetPerf can run both QUIC and TCP.
3. Linux MPTCP as the multihoming/multipath baseline.

Do not present plain TCP as the only competitor.

### Network/control baseline

Initial practical baseline:

~~~text
IPv6 forwarding
+ FRRouting
+ OSPFv3 / ECMP
+ BFD where appropriate
~~~

For local-repair comparisons, include a stronger fast-reroute baseline where practical.

TI-LFA / Segment Routing should be treated as the architectural reference for modern IP local repair. If an equivalent lab implementation is available, add it later as an experimental baseline.

### Architecture reference

SCION is useful as a packet-carried-path architecture reference.

It is not required in the first performance matrix, but later comparison should include packet path-state size, transit state, repair behavior, and path resolution behavior.

## 3. Where NetSynth is most likely to show value

### 3.1 Local change containment

Expected differentiator:

~~~text
internal link/path change
    ->
owner Scope updates hidden realization
    ->
parent STP unchanged
    ->
outer packet route code unchanged
~~~

Measure update radius, not just recovery latency.

### 3.2 Server / service Endpoint movement

This is stronger than ordinary client roaming.

Example:

~~~text
stateful service EID X
initially attached at L1

Channel active

service state moves / attachment changes

Binding:
    {L1}
 -> {L1,L2}
 -> {L2}

same EID
same Channel
new Path State
~~~

QUIC v1 is a strong client-migration baseline but does not generally make arbitrary server-address movement a transparent network identity primitive.

NetSynth should test both planned make-before-break and abrupt movement.

### 3.3 Multihoming and failover

One EID can publish several Locators without creating a separate identity model.

Compare NetSynth alternate Locator, QUIC path migration/multipath behavior where available, and MPTCP additional subflows.

The important metric is not merely throughput aggregation. Measure how much address/path/session machinery is needed to preserve the logical communication object.

### 3.4 Independent-message completion under loss

Later compare one TCP connection carrying framed messages, QUIC using one stream per independent message, and NetSynth native Messages.

Induce loss in one message and measure completion latency of unrelated messages.

TCP is expected to show connection-level ordering effects. QUIC is the strong comparison and may remove most of this advantage.

## 4. Where NetSynth should not claim an automatic advantage

Do not assume NetSynth wins raw steady-state throughput, congestion-control quality, minimum header size, encryption cost, single-path bulk transfer, or sub-millisecond local repair.

Modern TCP/QUIC/IP implementations are highly optimized.

If NetSynth cannot demonstrate a stronger architectural property than those systems, that is evidence against the current design.

## 5. First real data-plane profile

Create an experimental software profile, provisionally called NS-Soft/0.

This is an implementation profile, not a new architecture revision.

### 5.1 Link framing

Use raw Ethernet frames with a configurable experimental EtherType in the lab.

Do not encapsulate NetSynth inside IPv4, IPv6, UDP, or TCP.

This keeps measured NetSynth headers/state honest.

The test harness may use ordinary IP/SSH out-of-band for orchestration and telemetry. That management path is not part of the NetSynth data-plane result.

### 5.2 Linux packet I/O

Use:

~~~text
XDP
+
AF_XDP
~~~

for the first software dataplane.

Reason:

- custom EtherType parsing is straightforward;
- XDP can perform bounded hot-path lookup/update/redirect work;
- AF_XDP provides high-performance endpoint/slow-path user-space packet I/O;
- no kernel IP stack semantics are required;
- the same packet format can later be mapped to a programmable switch/NIC target.

Do not start with DPDK unless AF_XDP becomes the measured bottleneck.

### 5.3 Fast path

The XDP forwarding path should contain only the frozen small instruction set.

Conceptually:

~~~text
parse base NetSynth header
check version / bounds
decrement Hop Budget

if active local token:
    token -> BPF map lookup
    execute bounded action
else:
    consume next coarse Route-Code action

possibly update:
    current token
    route cursor
    bounded continuation context

redirect to output interface
~~~

No arbitrary loops or application logic.

### 5.4 Slow/control path

User space owns Scope topology, BTG/STP construction, route resolution, forwarding-program compilation, Binding resolution, Channel endpoint state, security, and forwarding-table installation.

Fast path sees only compiled local state.

## 6. Concrete implementation split

### nsd

Per-node NetSynth control daemon.

Responsibilities:

- local link/topology state;
- Scope ownership;
- STP lifecycle;
- forwarding-binding installation;
- route-resolution RPC;
- Binding Service client/server roles when configured.

### XDP program

Responsibilities:

- base-header validation;
- Hop Budget;
- local forwarding-token lookup;
- route cursor/context update;
- redirect/drop;
- explicit stale/unknown-token handling.

### libns

Endpoint user-space library.

Responsibilities:

- EID identity;
- Binding lookup/publication;
- route-program cache;
- Channel;
- Message reliability;
- path-specific congestion state;
- packetization;
- AEAD.

### nsperf

Purpose-built benchmark tool.

Workloads:

- ping/latency;
- fixed-size Messages;
- bulk transfer;
- many independent Messages;
- controlled migration;
- continuous transfer during failures.

Do not reuse TCP socket semantics internally merely to make the API familiar.

## 7. Experimental topology

### 7.1 Development topology

Start on one Linux machine using network namespaces and veth pairs.

Use a topology with:

~~~text
Client
  |
Ingress
  |
+---------------- Scope S ----------------+
|                                         |
|  boundary A -- path 1 -- boundary B     |
|       \          /                      |
|        -- path 2 --                     |
+-----------------------------------------+
  |
Egress
  |
Server attachment L1
Server attachment L2
~~~

Requirements:

- two internal routes in Scope S;
- one internal failure that S can hide;
- two destination attachment positions;
- at least one outer route whose code does not change during hidden repair.

Namespace/veth results are for semantics/control measurements, not line-rate claims.

### 7.2 Physical performance topology

After semantics are stable, move the same profile to dedicated Linux hosts/NICs.

Minimum useful roles:

~~~text
Endpoint A
Forwarder / Scope ingress
one or more Scope-internal forwarders
Forwarder / Scope egress
Endpoint B
~~~

Prefer ordinary Ethernet NICs with native XDP/AF_XDP support for the first line-rate study.

## 8. Benchmark matrix

### 8.1 Stable single-path baseline

Workloads:

- 64 B;
- 256 B;
- 1 KiB;
- 4 KiB Messages;
- large bulk transfer.

Concurrency:

- 1;
- moderate;
- high enough to saturate the link.

Measure:

- application goodput;
- packet rate;
- RTT / one-way latency where synchronized clocks are available;
- p50/p95/p99;
- CPU utilization;
- cycles per packet/byte where measurable;
- drops;
- forwarding lookups;
- route-code bytes;
- total header bytes;
- payload efficiency.

Baselines:

- TCP/CUBIC;
- QUIC/MsQuic;
- NetSynth.

Interpretation: this is a cost floor, not the primary expected NetSynth win.

### 8.2 Hidden local failure

Run continuous traffic and fail one Scope-internal link.

Compare IPv6 + FRR/OSPFv3 + BFD/ECMP, stronger FRR/TI-LFA reference when available, and NetSynth hidden STP repair.

Measure:

~~~text
failure -> first successful repaired packet
lost packets / bytes
application stall
routers/controllers touched
control messages / bytes
forwarding entries changed
parent-visible route updates
ingress route recompilations
~~~

Primary NetSynth success condition when the STP contract remains valid:

~~~text
parent-visible hard update count = 0
outer Route Code recompile count = 0
~~~

Recovery latency still matters, but local change containment is the architectural claim.

### 8.3 Planned Endpoint migration

Maintain an active long-lived transfer while moving the receiving service from L1 to L2.

NetSynth sequence:

~~~text
publish {L1,L2}
bring up L2
switch preferred path
withdraw L1
~~~

Compare TCP reconnect/application recovery, QUIC migration capabilities, MPTCP make-before-break, and NetSynth.

Measure application-visible stall, connection/Channel identity continuity, handshake count, retransmitted bytes, control traffic, path-validation time, and network nodes whose state changes.

### 8.4 Abrupt Endpoint movement

Remove L1 without overlap, then publish/resolve L2.

Measure the same metrics.

Run client movement and server/service movement separately. QUIC is expected to be strong on client movement.

### 8.5 Multihoming failover

Start with:

~~~text
EID -> {L1,L2}
~~~

Fail the active path.

Compare NetSynth, MPTCP and QUIC path migration/multipath implementation where available.

Measure failover interruption, control messages, new-path validation, retransmission, and whether application identity/state changes.

Do not initially measure simultaneous path striping because NetSynth v0.1 deliberately freezes one active sending path per direction.

### 8.6 Message independence under loss

Send many independent logical requests simultaneously.

Force one selected packet/message to be lost.

Compare framed messages over one TCP stream, one QUIC stream per independent message, and NetSynth native Messages.

Measure completion latency of messages unrelated to the lost one.

If QUIC performs equivalently, record that honestly.

## 9. Separate architecture metrics from implementation metrics

Architecture metrics:

- persistent forwarding state;
- parent-visible state;
- route-code bytes;
- Binding state;
- update radius;
- route recompilation count;
- Endpoint/Channel continuity;
- number of layers whose state changes.

Implementation metrics:

- ns/op;
- cycles/packet;
- Mpps;
- Gbit/s;
- cache misses;
- memory bandwidth;
- syscall/kernel-crossing cost.

A bad implementation is not automatically evidence that the architecture is bad. A highly optimized fast path is not proof that the architecture scales.

## 10. Fairness rules

### Same physical topology

All compared systems use the same links, rates, delays and failure schedule.

### Strong current baselines

Do not disable TCP CUBIC, QUIC encryption, reasonable NIC offloads, or BFD/fast reroute where part of the baseline.

If NetSynth security is enabled, compare to encrypted QUIC separately from plain TCP.

### Separate compatibility tax

NetSynth does not need to emulate 5-tuples, ports, IPv4/IPv6 addresses, UDP encapsulation, or middlebox traversal.

Report when a baseline cost exists mainly because it supports compatibility/deployment requirements.

Do not count removing compatibility as a theorem-level architecture win; count it as a clean-slate implementation advantage.

### No unfair transport comparison

Until NetSynth congestion control is mature:

- do not interpret bulk throughput difference as a fundamental transport result;
- use forwarding-only microbenchmarks to study the network data plane;
- use failure/mobility tests primarily for semantic disruption and state-transition cost.

## 11. Packet-format work after the benchmark skeleton

Do not optimize the final header before the test harness exists.

The first experimental profile should have a deliberately simple, inspectable encoding.

Only after measurements should optimize:

- field widths;
- EID representation on established Channels;
- Locator component packing;
- local forwarding-token widths;
- route-code compression;
- ACK/control framing;
- combined network/Channel headers.

For every field ask:

> Is this information actually unknown at the receiver/forwarder, or are we redundantly transmitting context already known there?

This is where clean-slate design can later remove TCP/IP-era redundancy.

## 12. First implementation milestone

The first real milestone is not a full NetSynth stack.

Build:

~~~text
custom L2 NetSynth packet
        |
        v
XDP forwarding on Route Code / local token
        |
        v
two-path Scope
        |
        v
local hidden STP repair
~~~

No Channel, Binding Service or security is required in the first milestone.

Success means:

1. real packets traverse multiple NetSynth forwarders;
2. route code and token state are visible/accounted;
3. an internal link failure changes only Scope-local forwarding state;
4. outer packet route code remains valid;
5. packet wire size remains fixed;
6. forwarding state/update counts are recorded automatically.

Then add Endpoint identity / Channel / mobility in the second milestone.

## 13. Second implementation milestone

Add:

~~~text
EID
Binding
Channel
AEAD
two attachment Locators
~~~

Then run planned and abrupt service migration.

This is the first milestone where comparison against TCP/QUIC/MPTCP becomes a central result.

## 14. Third implementation milestone

Only after the first two milestones are stable:

- optimize header representation;
- add path packet-size probing;
- tune batching/zero-copy;
- move more forwarding into native XDP;
- optionally produce a P4 implementation of the fixed hot path;
- run line-rate physical-NIC experiments;
- add larger control-plane/scaling experiments.

## 15. Go / no-go criteria

NetSynth has demonstrated meaningful value if at least one frozen architectural property yields a clear measurable benefit that strong modern baselines do not obtain without substantially more state or cross-layer machinery.

The strongest candidate claims are:

### Claim A: change containment

Internal physical repair can preserve the external STP and compiled outer route indefinitely, reducing control/update radius.

### Claim B: identity/location separation

Endpoint/service attachment can change while stable identity and reliable Channel survive without redefining communication around address tuples.

### Claim C: explicit resource placement

The forwarding compiler can trade packet bytes against reusable local state under hardware/context limits without exposing descendant topology.

If experiments show no meaningful advantage in these dimensions, the architecture should be reconsidered before adding features.

## 16. Immediate next task

Implement only milestone 1:

> raw-L2 NetSynth packets + XDP/AF_XDP forwarding + one two-path Scope + hidden local STP repair + resource telemetry.

Do not implement the full transport stack yet.
