"""Two hand-selected topologies and layouts, not a partition search or stretch sweep."""

from __future__ import annotations

from dataclasses import asdict, replace
from types import MappingProxyType

from netsynth.forwarding import Locator
from netsynth.graph import Edge, Graph
from netsynth.scale4 import ExecutionResult, RouteProgram, RouteQueryContext, execute_route_program
from netsynth.scale5 import (
    BindingService,
    Endpoint,
    EndpointID,
    EndpointPacket,
    LocalAttachment,
    deliver_endpoint_packet,
)
from netsynth.scale6 import ChannelEnvelope, EndpointChannels, establish_channel
from netsynth.scope_evolution import (
    FormationPolicy,
    LayoutGeneration,
    LayoutRoute,
    RoutingScope,
    control_budget,
    migration_cost,
)


def modular_graph() -> Graph:
    return Graph(
        set(range(10)),
        [Edge(left, right) for group in (range(5), range(5, 10)) for left in group for right in group if left < right]
        + [Edge(4, 5)],
    )


def poor_graph() -> Graph:
    # Dense cut, plus an intentionally cheaper leave/re-enter route for child {0,1,2}.
    return Graph(
        set(range(6)),
        [Edge(left, right, 100.0 if right < 3 else 1.0) for left in range(6) for right in range(left + 1, 6)],
    )


def layouts(
    graph: Graph, cut: int, name: str, prefix: tuple[int, ...]
) -> tuple[RoutingScope, LayoutGeneration, LayoutGeneration]:
    scope = RoutingScope(name, prefix, graph.nodes, frozenset({0, len(graph.nodes) - 1}))
    old = scope.prepare(0, graph, (graph.nodes,))
    scope.activate(0)
    new = scope.prepare(1, graph, (frozenset(range(cut)), graph.nodes - frozenset(range(cut))))
    return scope, old, new


def delivered(scope: RoutingScope, graph: Graph, route: LayoutRoute) -> bool:
    result = scope.execute(graph, route, 100)
    return isinstance(result, ExecutionResult) and result.status == "delivered"


def exhaustive_valid(scope: RoutingScope, graph: Graph, layout: LayoutGeneration) -> bool:
    """Only the two tiny fixtures; no metric/stretch/scaling experiment."""
    for source in sorted(graph.nodes):
        for target in sorted(graph.nodes - {source}):
            route = layout.compile(source, layout.locator(target))
            result = scope.execute(graph, route, 100)
            if not isinstance(result, ExecutionResult) or result.status != "delivered" or result.path[-1] != target:
                return False
            if any(graph.edge(left, right) is None for left, right in zip(result.path, result.path[1:], strict=False)):
                return False
    return True


def run_probe() -> dict[str, object]:
    graph = modular_graph()
    scope, old, new = layouts(graph, 5, "modular", (7,))
    parent_before = scope.export()
    old_budget, new_budget = control_budget(old, parent_before), control_budget(new, parent_before)
    transition_cost = migration_cost(old, new, old_budget, new_budget, affected_endpoints=2)
    policy = FormationPolicy()
    gain = policy.score(old_budget) - policy.score(new_budget)
    accepted_split = policy.evaluate(old_budget, new_budget, transition_cost, (gain, gain, gain))
    transient = policy.evaluate(old_budget, new_budget, transition_cost, (gain, 0, gain))
    small = policy.evaluate(
        old_budget,
        replace(old_budget, maximum_controller_records=old_budget.maximum_controller_records - 1),
        transition_cost,
        (1, 1, 1),
    )
    old_route = old.compile(0, old.locator(9))
    parent_handle = parent_before.pathlets[0].handle
    cached_parent_transit = RouteProgram(Locator((99,), 0), (parent_handle,))
    scope.activate(1)
    coexisting = old.phase == new.phase == "active"
    old.tree.validate(graph)
    new.tree.validate(graph)
    old_active = delivered(scope, graph, old_route)
    new_route = new.compile(0, new.locator(9))
    new_active = delivered(scope, graph, new_route)
    correct_modular = exhaustive_valid(scope, graph, old) and exhaustive_valid(scope, graph, new)
    binding_service = BindingService((old.locator(0),))
    mobile, local = Endpoint(EndpointID(b"renumbered-stable-eid")), EndpointID(b"local-peer")
    old_attachment, new_attachment = LocalAttachment(old.locator(9), 9), LocalAttachment(new.locator(9), 9)
    old_attachment.attach(mobile)
    first = binding_service.publish(mobile.eid, frozenset({old_attachment.locator}))
    local_endpoint = Endpoint(local)
    old_local = LocalAttachment(old.locator(0), 0)
    new_local = LocalAttachment(new.locator(0), 0)
    old_local.attach(local_endpoint)
    binding_service.publish(local, frozenset({old_local.locator}))
    left, right = EndpointChannels(local, lambda: b"A" * 16), EndpointChannels(mobile.eid, lambda: b"B" * 16)
    channel, peer = establish_channel(left, right, maximum_message_size=16)
    channel.replace_path(first, old_route.program, 96, 0)
    channel.queue_message(b"continuity")
    pending = channel.send_next(1)
    assert pending is not None
    new_attachment.attach(mobile)
    overlap = binding_service.publish(mobile.eid, frozenset({old_attachment.locator, new_attachment.locator}))
    new_local.attach(local_endpoint)
    binding_service.publish(local, frozenset({old_local.locator, new_local.locator}))
    old_delivery = deliver_endpoint_packet(
        graph,
        scope.registries(),
        old_route.access,
        old_route.context,
        100,
        EndpointPacket(mobile.eid, old_attachment.locator, old_route.program, repr(pending).encode()),
        old_attachment,
    )
    token_before = (channel.local_receive_token, channel.remote_receive_token)
    credit_before = channel.peer_credit_limit
    channel.replace_path(overlap, new_route.program, 100, 2)
    assert right.receive(ChannelEnvelope(pending), 3) == "accepted"
    assert left.receive(ChannelEnvelope(peer.make_feedback()), 4) == "accepted"
    channel_identity = (
        left.channels[channel.local_receive_token] is channel
        and channel.remote_eid == mobile.eid
        and token_before == (channel.local_receive_token, channel.remote_receive_token)
        and credit_before == channel.peer_credit_limit
        and channel.next_packet_number == 1
        and channel.next_message_id == 1
    )
    current = binding_service.publish(mobile.eid, frozenset({new_attachment.locator}))
    binding_service.publish(local, frozenset({new_local.locator}))
    old_local.detach(local)
    old_attachment.detach(mobile.eid)
    stale_registry_view = scope.registries()
    stale_child = old.child_btgs[0].pathlets[0].handle
    scope.retire(0)
    stale_route = scope.execute(graph, old_route, 100)
    raw_stale = execute_route_program(
        graph, stale_registry_view, old_route.access, old_route.program, old_route.context, 100
    )
    cached_parent = execute_route_program(
        graph,
        scope.registries(),
        MappingProxyType({}),
        cached_parent_transit,
        RouteQueryContext("parent-transit", parent_before.pathlets[0].ingress),
        100,
    )
    parent_preserved = (
        scope.export() == parent_before and scope.parent_hard_updates == 0 and cached_parent.status == "delivered"
    )
    assert delivered(scope, graph, new_route)
    poor = poor_graph()
    poor_scope, poor_flat, poor_split = layouts(poor, 3, "poor", (8,))
    poor_parent = poor_scope.export()
    flat_budget, split_budget = control_budget(poor_flat, poor_parent), control_budget(poor_split, poor_parent)
    poor_cost = migration_cost(poor_flat, poor_split, flat_budget, split_budget, 2)
    poor_gain = policy.score(flat_budget) - policy.score(split_budget)
    rejected_split = policy.evaluate(flat_budget, split_budget, poor_cost, (poor_gain, poor_gain, poor_gain))
    # Force the candidate only as a correctness negative control, not as a formation decision.
    poor_scope.activate(1)
    correct_poor = exhaustive_valid(poor_scope, poor, poor_flat) and exhaustive_valid(poor_scope, poor, poor_split)
    escape = poor_scope.execute(poor, poor_split.compile(0, poor_split.locator(1)), 100)
    leave_reenter = (
        isinstance(escape, ExecutionResult)
        and escape.path[0] == 0
        and escape.path[-1] == 1
        and any(node >= 3 for node in escape.path)
    )
    # The same hand-selected layouts also supply a merge candidate. No partition search.
    merge_cost = migration_cost(poor_split, poor_flat, split_budget, flat_budget, 2)
    merge_gain = policy.score(split_budget) - policy.score(flat_budget)
    merge = policy.evaluate(split_budget, flat_budget, merge_cost, (merge_gain, merge_gain, merge_gain))
    poor_scope.retire(0)
    merged_flat = poor_scope.prepare(2, poor, (poor.nodes,))
    poor_scope.activate(2)
    poor_scope.retire(1)
    merged_correct = exhaustive_valid(poor_scope, poor, merged_flat)
    return {
        "schema": "netsynth.scope-evolution.semantic-probe.v1",
        "parameters": {
            "seed": None,
            "candidate_source": "hand-selected-only",
            "policy": asdict(policy),
            "metric_units": "normalized-records; amortized over declared toy horizon",
            "affected_endpoints": 2,
            "generations": {"modular": [0, 1], "poor": [0, 1, 2]},
            "correctness_pairs": "exhaustive ordered pairs on two tiny graphs",
        },
        "topologies": {"modular": graph.to_dict(), "poor": poor.to_dict()},
        "budgets": {
            "modular_flat": asdict(old_budget),
            "modular_split": asdict(new_budget),
            "poor_flat": asdict(flat_budget),
            "poor_split": asdict(split_budget),
        },
        "migration": {
            "modular_split": asdict(transition_cost),
            "poor_split": asdict(poor_cost),
            "poor_merge": asdict(merge_cost),
        },
        "results": {
            "modular_split": accepted_split,
            "poor_split": rejected_split,
            "poor_selected_layout": "flat" if rejected_split != "accept" else "split",
            "merge_candidate": merge,
            "transient_gain": transient,
            "small_gain": small,
            "old_binding_version": first.version,
            "overlap_binding_version": overlap.version,
            "new_only_binding_version": current.version,
            "stale_old_route": stale_route if isinstance(stale_route, str) else stale_route.status,
            "stale_raw_executor": raw_stale.status,
            "parent_hard_updates": scope.parent_hard_updates,
            "leave_reenter_path": escape.path if isinstance(escape, ExecutionResult) else (),
            "query_local_access_records": sum(registry.charged_records for registry in new_route.access.values()),
        },
        "criteria": {
            "coexistence_individually_laminar": coexisting,
            "generation_qualified_locators_never_alias": all(
                old.locator(node) != new.locator(node) for node in graph.nodes
            ),
            "EID_channel_survive_renumbering": channel_identity and overlap.eid == first.eid == current.eid,
            "old_program_runs_while_active": old_active and old_delivery.status == "delivered",
            "new_program_compiles_executes": new_active,
            "retired_layout_fails_closed": stale_route == "stale_layout"
            and raw_stale.status == "missing_access_state"
            and stale_registry_view[stale_child.owner_scope].lookup(stale_child) is None,
            "preserved_STP_has_no_parent_hard_update": parent_preserved,
            "no_global_configuration_epoch": scope._generation_floor == 1
            and poor_scope._generation_floor == 2
            and scope.prefix != poor_scope.prefix,
            "budget_charges_local_parent_boundary_BTG": old_budget.local_total_records > 0
            and new_budget.child_boundary_records > 0
            and new_budget.child_btg_pathlet_records > 0
            and new_budget.parent_visible_records == parent_before.persistent_records,
            "migration_and_binding_cost_explicit": transition_cost.renumbered_attachments == 10
            and transition_cost.binding_publications == 4
            and transition_cost.overlap_records > 0,
            "hysteresis_rejects_small_transient": transient != "accept" and small != "accept",
            "modular_split_accepted": accepted_split == "accept",
            "poor_topology_can_remain_flat": rejected_split != "accept" and merge == "accept" and merged_flat.flat,
            "correctness_independent_of_layout": correct_modular and correct_poor and merged_correct and leave_reenter,
        },
    }
