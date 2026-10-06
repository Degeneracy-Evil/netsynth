# Tiny Forwarding Program semantic validation

Status: selected hybrid model validated. The architecture semantics are frozen by `forwarding-program-freeze-review.md`; this remains a semantic validation, not a wire-format or performance freeze.

## Reconciliation and scope

- Mathematical abstraction: compilation of a compositional route into packet
  instructions, reusable local macros and bounded writable working context.
- Closest established problems: compact routing and path encoding with installed
  forwarding entries; Binding Segments and pathlet/FID composition are prior art.
- Known upper bounds: existing path-encoding constructions trade local entries
  against packet instructions; this prototype makes no optimality claim.
- Known lower bounds / hardness: the
  [existing reconciliation](packet-carried-routing-theory-reconciliation.md)
  records compact-routing trade-offs and APX-hard optimal path encoding.
- Known constructions: inline hops, local macro bindings and reserved
  continuation context, not a new routing algorithm.
- Why these do not fully answer NetSynth: immediate-child-only knowledge,
  opaque repairable STPs, exact generations and non-growing ingress allocation
  must hold simultaneously.
- NetSynth-specific question: can the selected hybrid execute the same abstract
  route with bounded context, transferring excess continuation information into
  reusable state without exposing hidden descendant paths?
- Minimal experiment: one 10-node, four-level laminar fixture; repeated calls
  leave/re-enter a leaf, followed by a longer hidden repair and hard withdrawal.

No path selection, optimal encoding search, scaling, PMTU probing, congestion
benchmarking or changes to frozen Scale-4/5/6 modules are included.

## Implementation

`forwarding_program.py` is an encoding adapter, not a routing framework.
The existing Scale-4 Route Program executor remains the physical-path oracle.

Each owner compiles only its own validated STP actions. Child compilation is an
opaque owner-local request through `ChildCompiler`: a hard advertisement with
a conservative context-word requirement and an install operation accepting a
context capacity plus an opaque caller continuation. Successful installation
commits to that capacity. The parent cannot access child realizations through
this interface. Tests replace child implementations with interface-only proxies.

Hybrid Packet Route Code contains the two root-owned crossings and one opaque
middle-Scope token, never the leaf's physical path. Owner-local instructions
perform physical hops, invoke immediate children, or return. Context slots are
allocated before execution; there is no other execution continuation stack.
Three fixed words model cursor/current token/depth. A child call either consumes
a reserved slot or installs a continuation-specialized reusable child binding.
Identical calls reuse entries, independent of packet, EID, flow or Channel.

The state-heavy control installs the same whole abstract sequence as a root
macro. The packet-heavy control deliberately expands descendant realizations
with ancestry generation guards: it is a **privileged knowledge control**, not
an alternative proposed NetSynth architecture. This privilege is reported.

Execution dispatches only the current owner table and exact local generation
guard. The harness holds all registries and the physical graph to check hops;
neither global object is passed to a hybrid compiler. It performs no path
planning or hidden target-membership queries during forwarding.

## Reproducible result

Run:

```bash
uv run --locked python src/forwarding_program_main.py
uv run --locked python scripts/check.py
```

Output has schema `netsynth.forwarding-program.semantic.v1`, fixture/seed,
accounting profile, before/repair physical paths, packet sizes and operation
counts. These byte counts are a declared symbolic profile (8-byte words,
12-byte exact handles, 1-byte opcodes), **not serialization or measured memory**.
The 64-byte network/Channel/security envelope is an explicit aggregate budget,
not a proposed framing format.

Before repair, on the identical abstract route:

| Encoding | Code bytes | Reserved context bytes | Binding entries | Binding/compiler state bytes | Payload at 512 bytes |
| --- | ---: | ---: | ---: | ---: | ---: |
| packet-heavy control | 318 | 24 | 0 | 32 | 106 |
| state-heavy control | 9 | 24 | 19 | 1059 | 415 |
| hybrid, 2 continuation slots | 27 | 40 | 12 | 668 | 381 |
| hybrid, 0 continuation slots | 27 | 24 | 15 | 839 | 397 |

The state byte charge includes instructions, tokens, hard resource caches,
variant keys/reference lists and monotonic token allocators, including the
32-byte idle allocator cost in the packet-heavy control. Frozen STP storage is
charged separately in records; it is not hidden in the binding byte comparison.
Runtime output separately charges binding lookups, exact-generation checks and
writable-context mutations. Generation checks are also local table reads, not
free lookups. Update counts include deleted and written binding records and
the underlying repaired STP realization, plus changed ingress code bytes.
Figures are logical costs, not throughput or timing claims.

All encodings follow `0,1,2,3,5,1,2,3,6,7,9`. After repair they follow
`0,1,4,8,3,5,1,4,8,3,6,7,9`, matching the frozen executor. Full-capacity
packets remain exactly 512 bytes at every observed forwarding action.

Hybrid and state-heavy preserve ingress code through repair. Only the leaf
binding table changes: 7 records with two slots, 14 with zero slots. Parent
tables have zero updates. Packet-heavy must recompile at ingress: its code
increases from 318 to 408 bytes and payload capacity decreases accordingly,
**never by growing an already transmitted packet**.

The size rule is explicitly checked before execution:

```text
usable size - route code - reserved context - envelope = payload capacity
```

Insufficient total size rejects packetization. Insufficient actual allocated
context fails closed if an intentionally malformed packet bypasses compilation;
normal compilation spills into bindings. Hop-budget exhaustion, missing physical
links and stale exact STP generations fail explicitly. A newer generation cannot
rescue or alias a stale compiled token. Resource-growing repair is rejected
before activation and requires a new hard generation.

## Freeze assessment / limitations

All requested static validation criteria pass, with no hidden descendant
dependency in hybrid and no packet-growing action. Packet-heavy moves detail
and repair cost to ingress/packet code; state-heavy moves choices and
continuations to tables; hybrid retains coarse packet choices and trades
reserved context against reusable specialized entries. No optimality or general
scalability follows from these four points.

The prototype executes boundary-to-boundary transit programs, not endpoint
delivery or PMTU negotiation. Existing opaque query-time Access, Channel and
security behavior remains covered by unchanged regression tests.

The freeze review resolves the remaining in-flight continuation boundary conservatively. Same-generation repair preserves the external STP contract and future outer-route compilation, but does not promise lossless survival of packets already executing retired internal continuation state. Such stale local references fail closed and may be recovered by the reliable Channel through ordinary retransmission. The common architecture therefore does not require draining, reference counting or multi-version continuation tables. Binding-state admission/GC policy and concrete wire widths remain implementation/profile choices.
