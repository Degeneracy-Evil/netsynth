Mathematical abstraction: a versioned flat-key identifier-to-Locator-set map, demand caching, and exact local delivery.

Closest established problems: identifier/locator separation, mobile rendezvous, cached mapping consistency, and association continuity.

Known upper bounds: authoritative records require O(Endpoints × replication factor) storage; the prototype models one logical record per EID, without a replica implementation.

Known lower bounds / impossibility: stale mapping caches cannot guarantee uninterrupted delivery after arbitrary movement. EID validation protects identity, not availability.

Known constructions: the resolver/cache/authority split and identity-preserving associations adopted in the Scale-5 architecture documents from HIP, LISP, MobilityFirst, and transport migration prior art.

Why these results do not fully answer NetSynth: they do not validate composition with the frozen Scope/STP/Route-Program ownership model.

NetSynth-specific question: can Endpoint movement replace edge binding/route state while preserving transit routing state and exact Endpoint identity?

Minimal experiment required: one five-node graph, two fixed attachment positions, a moved Endpoint, a replacement at its old position, and two independently stale caches.

# Scale-5 prototype validation

Run `uv run --locked python src/scale5_main.py` for JSON schema `netsynth.scale5.semantic-probe.v1`.
Run `uv run --locked python scripts/check.py` for the complete non-mutating repository checks.
All Scale-4 source and tests remain unchanged.

## Freeze evidence

| Architecture-audit criterion | Evidence |
| --- | --- |
| Stable EID during movement | Versions 1/2/3 keep the same opaque EID. |
| Simultaneous Locators | One Endpoint delivers at both positions; binding overlap contains both. |
| Scale-4 state unchanged | Scope, boundary ownership, BTG, STP realization/generation and routing state snapshots compare equal before/after movement. |
| Stale delivery is identity-safe | Old route reaches node 3, whose replacement Endpoint receives nothing; final delivery returns `eid_absent`. |
| Fresh lookup and route replacement | Explicit authority read selects the current Locator; a new Route Program reaches node 4 and delivers. |
| Ordered per-EID versions | Delayed older responses are rejected by resolver and association; conflicting equal-version records fail. |
| No global invalidation | Second resolver continues returning version 1 after the first refreshes to version 3. |
| Resolver bootstrap by Locator | Resolver and authority group locations are Locators; reads explicitly address the selected authority Locator; direct infrastructure programs execute before binding-service creation. |
| EID-keyed mock continuity | The same association and upper-state object survive Locator/program replacement. |
| Locator-only traffic | Original Scale-4 executor works without EID, binding service or local Endpoint table. |

The five-node probe has 5 sequential actions and maximum STP recursion depth 1.
Scale-5 state consists of 1 authority record, 2 resolver cache records, 2 local Endpoint records and 1 mock association.
No EID records enter Scale-4 transit state. Locator selectors continue identifying forwarding attachment positions;
multiple Endpoints can share one such position and are demultiplexed locally by EID.

All ten audit freeze criteria pass within this semantic model. The implementation adds no Channel object.

## Choices, ambiguities and limits

- `BindingVersion` is the name used here; the first identity document also uses `BindingGeneration`. Both mean per-EID ordered replacement state.
- Publication is serial/atomic at an in-memory logical authority group. SHA-256 modulo a fixed group count is only toy sharding; group membership changes, replica agreement, persistence and authority availability are unmodeled.
- Resolver/authority calls model control RPCs addressed by Locator. Actual control traffic transport and failure notification are not simulated.
- Cache lifetime uses resolver-local logical ticks. Expired entries retain their last binding as a version floor; cache eviction/reclamation is unmodeled and storage is charged as demand records. Delayed duplicate responses do not extend validity; an explicit authoritative revalidation can.
- Attachment installation/removal and authority publication are explicit independent events. Stale windows are safe through final EID checking; uninterrupted handover is not promised. Binding records are not evidence of physical reachability.
- Locator selection uses deterministic ordering only for the fixture. Locator quality/preferences and retry policies remain unspecified.
- The edge reacts to `eid_absent` by explicit fresh lookup and recompilation. The mock records successful delivery only; it defines no retransmission, ordering, congestion or transport migration policy.
- EID bytes and random-generation width are prototype choices. Uniqueness/publication authority is assumed; security, identity takeover, source identity and human naming remain deferred as documented.
