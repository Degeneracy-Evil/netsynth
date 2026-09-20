# Scale 4 Semantic Prototype Review

> Reviewed commit: d79cb4444c131e1683d6613150dc8ad35b299b30.
>
> Result: the prototype validates several intended Scale-4 ideas, but Scale 4 must **not** be frozen yet. The implementation still permits hidden descendant topology leakage and malformed pathlet contracts. These are semantic issues, not merely missing tests.

## What is already correct

The prototype successfully keeps the work narrowly scoped:
- no generic routing-framework refactor;
- no Phase-6 experiment machinery;
- no broad state/stretch sweep.

It also demonstrates several intended semantics:
- parent route selection over child BTGs and crossing links;
- leave/re-enter paths across child Scopes;
- packet execution through reusable pathlet handles;
- recursive pathlet invocation;
- separate sequential Route-Program length and recursive stack depth;
- hidden pathlet repair preserving a cached top-level Route Program;
- soft metric changes preserving hard generation identity;
- fail-closed stale generations;
- Scale-0/1/2/3 degeneration with no Scale-4 route state.

These are useful and should be retained.

## Blocking issue 1: parent pathlets may directly encode descendant physical topology

PathletRegistry validates a PhysicalHop only by checking that both endpoints belong to the owner Scope.

For a non-leaf Scope, this permits a parent-owned pathlet realization to contain arbitrary PhysicalHops entirely inside a descendant child.

That violates the architecture boundary:

> a parent may use immediate-child pathlet contracts and parent-owned crossing links, but may not encode descendant interior physical hops.

The same validator permits a pathlet to reference a PathletHandle from **any proper descendant**, not only an immediate child.

This lets an ancestor skip ownership layers and retain grandchild routing handles directly.

### Required fix

For a non-leaf owner Scope, a persistent realization may contain only:
- physical crossing actions owned at that Scope level;
- pathlet handles exported by immediate children.

For a leaf Scope, local physical hops are allowed.

Do not give the parent a descendant Graph merely to validate this. Give the owner-level registry/control object only the physical actions and immediate-child contracts it is allowed to know.

## Blocking issue 2: Access Offers are not actually opaque

RouteQueryContext stores flattened AccessRealizations at the requesting/source side.

A remote DestinationAccessOffer can therefore expose:
- physical hops inside the destination child;
- lower-level pathlet handles;
- descendant route structure.

That contradicts the Scoped Route Resolution design, where an Access Offer is an opaque query result owned by the child that generated it.

### Required fix

Keep query-local realization state at the owning Scope.

A Route Program may carry an opaque AccessHandle, but execution must resolve that handle through an owner-local ephemeral query registry/service.

The parent/ingress may know:
- owner Scope;
- boundary endpoint;
- query handle;
- soft query cost.

It must not receive the realization.

Source and destination Access Offers should use the same ownership rule.

## Blocking issue 3: advertised pathlet contracts are not validated structurally

publish() and repair() validate action types and coarse Scope membership only.

They do not prove that the realization:
- starts at the advertised ingress;
- is action-by-action continuous;
- ends at the advertised egress.

They also do not validate that a PhysicalHop is one of the owner-level physical actions the Scope is allowed to use.

As a result, a malformed advertised contract can enter persistent state and fail only when a packet executes it.

That violates the hard STP guarantee: an active advertised generation is supposed to be realizable.

### Required fix

Validate a pathlet realization against the advertised contract before publication/repair.

Validation should use only:
- owner-level physical crossing/local-link contracts;
- immediate-child advertised pathlet ingress/egress contracts.

No descendant realization may be opened.

The validator must check complete action continuity and advertised ingress/egress equality.

## Blocking issue 4: parent Route Service construction sees full child membership

ScopeRouteService receives a full Scope object and builds child_by_node from every child member.

It later discards that information, so runtime persistent state is cleaner than the constructor, but the semantic boundary should also hold at construction.

A parent Route Service needs immediate-child identity, boundary ownership, child BTGs, and parent-owned crossing links. It does not need the complete interior member sets of every child.

### Required fix

Construct ScopeRouteService from a parent-level view, not a full descendant-membership Scope object.

Crossing validation should use boundary ownership / immediate-child interfaces rather than all interior members.

The simulator builder may know the full topology in order to instantiate objects, but that knowledge must not enter the Route Service API/state.

## Blocking issue 5: retired-generation state grows without bound

The _retired set retains every historical PathletHandle forever.

This prevents aliasing, but it creates unbounded persistent state under repeated repair/republication.

### Required fix

Use a per-slot monotonically increasing generation high-water mark (or equivalent bounded-by-number-of-slots semantic state).

An old exact handle then remains distinguishable from the active higher generation without retaining one tombstone per historical generation.

Exact finite-width wraparound policy can remain deferred, but the semantic prototype must not require an ever-growing retired-handle set.

## Additional hardening

Access offers should be validated against parent-visible boundary ownership:
- offer.boundary belongs to the BTG of offer.handle.owner_scope;
- owner_scope is an immediate child;
- all offers in one request use the correct query identity.

Keep the existing explicit runtime statuses and physical-hop validation.

## What does not need redesign

Do not change:
- Structured Locator;
- BTG/STP architecture;
- push-summary/pull-route split;
- Route Program / Transit Stack semantics;
- hard generation vs soft metric split;
- leave/re-enter support.

The issues are enforcement/ownership bugs in the prototype, not evidence against the Scale-4 architecture.

## Exit criteria for the hardening pass

Scale 4 may be frozen only after tests demonstrate:

1. an ancestor pathlet cannot contain descendant interior PhysicalHops;
2. an ancestor cannot directly reference a non-immediate descendant pathlet;
3. Access Offer realizations remain owner-local and opaque to parent/ingress;
4. every published/repaired STP is continuous from advertised ingress to egress;
5. validation uses only owner-visible contracts;
6. parent Route Service receives no child interior membership/topology;
7. generation reuse safety requires O(active slots) semantic history, not O(all historical generations);
8. the previous leave/re-enter, recursive execution, hidden repair, soft metric and fail-closed tests still pass.

After that, no further Scale-4 routing mechanism should be added unless the hardened prototype exposes a new architectural contradiction.
