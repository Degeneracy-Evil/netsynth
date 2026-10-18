# NetSynth

NetSynth is a clean-slate computer-network architecture research project.

The project derives a network architecture from first principles, introducing new abstractions only when the previous model fails. Compatibility with Ethernet/IP/TCP/BGP/DNS is not a design requirement, but established mathematics and modern systems work are mandatory constraints and sources of reusable ideas.

## Current architecture

The primary architecture entry point is [`docs/architecture-v0.1.md`](docs/architecture-v0.1.md).

Related project guidance:
- [`docs/architecture-recentering.md`](docs/architecture-recentering.md): research direction and methodology;
- [`AGENTS.md`](AGENTS.md): implementation/research rules for coding agents.

The current architecture includes Routing Scopes, Boundary Transit Graphs and opaque Scoped Transit Pathlets, Structured Locators, pull-based route resolution, stable Endpoint IDs with versioned bindings, reliable unordered Message Channels, a minimal Security Floor, and versioned Scope layouts for structural evolution.

Service naming and group communication remain above the common core.

NetSynth Architecture v0.1 is now semantically frozen. Its forwarding plane uses a hybrid compiled model: packets carry finite coarse Route Code, while Scopes retain reusable local forwarding bindings and packets reserve bounded writable forwarding context. See `docs/architecture-v0.1-freeze-review.md`.

## Research-value status (October 2026)

The frozen v0.1 architecture is a coherent semantic systems design, **not yet a demonstrated novel routing architecture**. A strong combination of hierarchical pathlets, Segment Routing / Binding SIDs, QoS summary policies, identity/location separation and message-oriented transports covers much of its claimed functionality.

See [the research-value gate](docs/research-value-gate-2026-10.md) and [the bounded expressiveness-equivalence challenge](docs/expressiveness-equivalence-gate-2026-10.md). Pause large simulator rewrites and full-stack/XDP work until a credible remaining architectural capability or resource separation has been identified. This assessment does not alter frozen v0.1 semantics.

The current first-principles resource study is [resource economics and break-even](docs/first-principles-resource-economics-2026-10.md). A useful systems result need not be a brand-new theoretical mechanism: comparable performance and semantics with a measured reduction in transmitted bytes, CPU, resident state, or control traffic is sufficient engineering value. These are hypotheses, not yet measured results.

## Semantic prototypes

Tiny deterministic probes validate frozen architecture choices:

```bash
uv run --locked python src/scale4_main.py
uv run --locked python src/scale5_main.py
uv run --locked python src/scale6_main.py
uv run --locked python src/security_floor_main.py
uv run --locked python src/scope_evolution_main.py
uv run --locked python src/forwarding_program_main.py
uv run --locked python scripts/check.py
```

These probes validate semantics and ownership boundaries. They are not performance benchmarks or production protocol implementations.

The [forwarding-program validation](docs/forwarding-program-validation.md) compares packet-heavy, state-heavy and hybrid encodings on one tiny topology, including bounded-context spilling and a longer hidden STP repair.

## Tiny resource-cost validator

```bash
uv run --locked python src/resource_economics_main.py
uv run --locked python src/resource_economics_main.py --control-hops 4
uv run --locked python scripts/check.py
```

This is deterministic resource accounting on the existing 10-node Forwarding
Program fixture, not a new routing mechanism or performance benchmark. JSON
includes workload/seed/schema, assumptions, physical paths, header byte-hops,
binding/compiler and ingress-cache state, lookups, mutations, update messages,
record work, stale failures, and separate Pareto dimensions.

Explicit forwarding carries existing hybrid code/context (27+40 bytes);
the shared-token variant uses the existing reusable whole-program macro
(9+24 bytes). Both retain owner-local opaque STP bindings. The cold explicit
case is **not** the privileged descendant-expansion packet-heavy control.
The token policy sends one explicit packet per cold cache lifetime and eagerly
installs a reusable macro; this intentionally loses on short lifetimes. No
lookahead-based admission policy has been added to hide that counterexample.

The equal-capability hierarchical SR/BSID **abstract** baseline gets the same
actions, widths, generation safety, local repair, caches, and explicit/token
choice. Its resource equality is derived by the restricted translation in the
[equivalence gate](docs/expressiveness-equivalence-gate-2026-10.md), **not an
independent measurement of deployed SR-MPLS/SRv6**. This validator therefore
does not establish an architectural advantage over strong SR/BSID.

Assumptions are explicit and shared by both architectures:

- Existing semantic profile: 8-byte words, 12-byte hard handles; counted sizes
  are neither serialized packets nor Python/ASIC resident-memory measurements.
- An illustrative established envelope is 34 bytes: flags/Hop Budget 2,
  Receive Token 4, PN 4, Message ID 4, fragment metadata 4, AEAD tag 16.
  Widths other than the standard tag are hypotheses, not frozen formats or a
  proof of transport/security equivalence. Total modeled headers are 101 bytes
  explicit and 67 bytes warm, **not the note's hypothetical 38-byte target**.
- Control distance defaults to 2 hops one way and is configurable. A changed
  owner receives one delta batch plus an acknowledgement: two envelope charges,
  an 8-byte acknowledgement, deleted token records (1+8 bytes) and written
  token/instruction records (1+8+existing instruction size). Query request is
  handle+capacity (12+8); response is code+bound (code length+8), plus two
  envelopes. STP realization replacements and hard handle updates are counted
  separately; unchanged contract metadata is already retained locally.
- Same 128-byte useful payload per successful packet, 512-byte ingress limit;
  actual traced path lengths are charged, including the longer repair detour.
  Channel setup, ACK/flow-credit traffic and physical failure discovery are
  excluded equally. This is not a full-stack secure/reliable byte-cost total.
- Ingress cache expiry causes a charged query, not fake table reinstallation.
  Hard withdrawals fail stale references closed; retry/fallback work is counted.
  In this fixture the stale whole-program token is rejected at ingress, so the
  failed attempt consumes lookup work but zero physical byte-hops; detection
  time and recovery latency are unmeasured, not assumed to be zero.
  Retired compiled entries remain charged: no unimplemented GC is assumed.
  Unshared cases are successive short hard-generation lifetimes, not identical
  routes artificially charged once per Channel. Simultaneously distinct-route
  state is not characterized by this single-route fixture.

Default results (positive means token saves **network byte-hops**, including
incremental control; it does not subtract RAM or work):

| Deterministic workload | Net saved byte-hops |
| --- | ---: |
| Long flow, 1024 packets | 346110 |
| One-packet short flow | -1710 |
| 32 Channels sharing one program, 128 packets total | 41470 |
| 16 unshared one-packet hard-generation lifetimes | -104400 |
| 8 batches of 16 packets, hidden repair between batches | 41634 |
| 8 batches of 4 packets, physical detour plus program replacement | -24192 |
| 8 batches of 8 packets, ingress cache expiry | 15860 |
| 8 batches of 4 packets, stale cached program then retry | -24192 |

For the static lifetime, incremental control is 1710 byte-hops and warm packets
save 34 bytes/hop over 10 traced hops. With one cold packet, strict break-even
is `(N-1)*10*34 > 1710`, hence **7 packets**, only for this declared profile.
Long-flow binding/compiler state rises from 668 to 1635 modeled bytes and total
binding/generation lookups from 30720 to 38904: saving traffic is **not Pareto
dominance**. Sharing across 32 Channels does not replicate transit entries.

Standard references are separate: IPv6 40 bytes
([RFC 8200](https://www.rfc-editor.org/rfc/rfc8200.html)), UDP 8 bytes
([RFC 768](https://www.rfc-editor.org/rfc/rfc768.html)), QUIC short header
1+CID+PN bytes ([RFC 9000 §17.3.1](https://www.rfc-editor.org/rfc/rfc9000.html#section-17.3.1)),
and a 16-byte AEAD tag ([RFC 8439](https://www.rfc-editor.org/rfc/rfc8439.html)).
CID=8/0 and PN=2 give **75/67 bytes**, excluding frames, ACKs and handshakes;
zero CID has usage restrictions and is not a mobility-equivalent baseline.
A single MPLS label is 4 bytes ([RFC 3032](https://www.rfc-editor.org/rfc/rfc3032.html)),
**not a complete version-safe secure packet**. BSID opacity/policy indirection
is established prior art ([RFC 9256](https://www.rfc-editor.org/rfc/rfc9256.html)).
These reference numbers do not establish equivalent unordered-Message service,
goodput, CPU or tail latency. The economics performance/value gate remains open.

## Actual-wire, node-local forwarding feasibility

```bash
uv run --locked python src/wire_feasibility_main.py
uv run --locked python scripts/check.py
```

Based on `e3f1356`, this tiny follow-up uses real big-endian serialized packets
and **two independent forwarding engines**, not copied baseline cost results.
NetSynth lowering consumes owner-local instructions, immediate-child entry
advertisements and opaque caller-return keys. Physical nodes retain only local
tables, local generation guards and physical neighbor ports. Neither data plane
receives a graph, owner map or registry. Tests delete all control/global maps
after installation and still deliver through neighbor links alone.

One experimental NetSynth header is:

```text
prefix 12 | current Scope/Token/generation 10 | Structured Locator 7
| immutable code 10*N | pre-reserved context 10*C
| Receive Token/PN/Message/fragment 16 | encrypted payload | AEAD tag 16
```

The prefix contains version/flags/Hop Budget/congestion mark (4 bytes), header
and packet lengths (4), and code count/cursor/context capacity/depth (4).
Keys contain Scope=16, Token=32 and generation=32 bits; Scope zero is reserved.
The fixture Locator contains one 16-bit component plus a 32-bit selector and
an 8-bit component count. These are **candidate widths, not a protocol freeze**.
Exhausted widths reject rather than wrap; generation `0xffffffff` is reserved
for inactive guards. Root crossing tokens use a disjoint reserved numeric range.

Initial result on the same 10-hop leave/re-enter route:

| Encoding | Actual header bytes | Node table rows | Serialized node state bytes | Table / generation reads |
| --- | ---: | ---: | ---: | ---: |
| NetSynth warm reusable macro | 71 | 19 | 931 | 19 / 19 |
| NetSynth explicit, 2 context slots | 111 | 14 | 726 | 17 / 17 |
| NetSynth explicit, 0 context slots | 91 | 17 | 837 | 17 / 17 |
| Independent single-label swapping | 49 | 16 | 564 | 16 / 16 |

**The old 67-byte estimate is not met by this candidate.** Locator, framing,
version and congestion fields add 13 bytes relative to its envelope; real packed
routing code/context save 9 against the old 8-byte-word profile, for net +4.
These figures are not lower bounds: there is no compression optimization here.
The label candidate is a preserved counterexample, not a NetSynth victory.

The baseline independently compiles the same opaque scoped policies into
continuation-specialized local LFIB entries. Its 4-byte label/TC/bottom/TTL shim
follows the field layout in [RFC 3032](https://www.rfc-editor.org/rfc/rfc3032.html#section-2.1);
it adds the **same** Locator, transport fields and AES-GCM protection. It is not
a complete deployed MPLS/SR stack. Exact local generation guards plus monotonic,
never-reused 20-bit labels provide fail-closed semantics over the tested finite
lifetime; exhaustion rejects. Unlimited safe label recycling is not claimed.

Both implementations preserve the outer code/label across a longer leaf repair,
deliver the same repaired 12-hop route, reject stale generations, and allow an
already-in-flight retired continuation to fail closed. Repair changes only leaf
nodes, not ancestor-owned entries. Packets filled to the 512-byte ingress limit
remain exactly 512 bytes; context shortage never enlarges them. Unknown local
tokens, malformed lengths, link loss, Hop-Budget exhaustion, corrupt ciphertext
and exhausted label space remain explicit negative cases.

JSON includes complete packet hex, per-node counts, state breakdowns, independent
operation counters per execution phase, and repair delta records/encoded bytes.
State is an exact canonical fixed-record image: NetSynth rows are 37 bytes,
label rows 21; both charge generation records (10 bytes) and neighbor interfaces
(4), with the label allocator watermark (4/node) also charged. These are **not
CPython heap or ASIC memory measurements**. Scope compiler caches/allocators and
endpoint keys/reliability state are outside these node-forwarding images, not
claimed free or included in a whole-system memory comparison.

AES-GCM is an endpoint-only integrity witness using isolated deterministic test
traffic keys; nonce prefixes are endpoint context and PNs must not wrap. This
does not implement handshake, message reliability, control-plane wire transport,
asynchronous update consistency, structural layout transitions or performance
benchmarks. No frozen v0.1 module or architectural semantics are changed.

## Historical experiments

The repository still contains Phase 1-5 routing/decomposition experiments and scaling studies. They remain useful as derivation history, negative controls, regression infrastructure, and evidence about state/stretch/churn and hierarchy failure modes.

Their prefix-monotone forwarding and metric-aware hierarchy designs are **not** the current NetSynth architecture.

Historical documents such as [`docs/architecture.md`](docs/architecture.md) and [`docs/simulator.md`](docs/simulator.md) are derivation records, not current architecture authority.

## Research method

```text
architecture question
    -> theory / prior-art reconciliation
    -> explicit NetSynth choice
    -> minimal semantic validation
```

Do not use large simulator sweeps to rediscover established theory, and do not turn every theoretical alternative into a first-class NetSynth abstraction.

## Development

The codebase uses Python 3.14, uv, Ruff, strict mypy, and pytest.

```bash
uv run --locked python scripts/check.py
```
