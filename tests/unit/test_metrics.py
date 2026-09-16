"""Phase-2 metric-definition tests."""

from netsynth.decomposition import BalancedConnectedDecomposition
from netsynth.failures import single_link_events
from netsynth.metrics import churn, failure_locality, path_quality, routing_state
from netsynth.routing import CompressedRouting, FlatRouting
from netsynth.summaries import SummaryBuilder, SummaryConfig
from netsynth.topology import mesh2d, tree


def test_flat_self_comparison_has_unit_weighted_and_hop_stretch() -> None:
    graph = tree(8)
    tree_control = BalancedConnectedDecomposition(3).decompose(graph)
    flat = FlatRouting(graph)
    result = path_quality(graph, flat, flat, [(0, 7), (3, 5)], tree_control, sampled=True)

    assert result["weighted_cost_stretch"]["mean"] == 1.0
    assert result["hop_count_stretch"]["mean"] == 1.0
    assert result["sampled"] is True


def test_state_and_churn_include_all_semantic_categories() -> None:
    graph = mesh2d(4, 4)
    tree_control = BalancedConnectedDecomposition(3).decompose(graph)
    builder = SummaryBuilder(tree_control, graph, SummaryConfig("s2", landmark_count=2))
    before_build = builder.build(graph)
    event = single_link_events(graph, tree_control)[0]
    after_build = builder.build(event.apply(graph))
    before = CompressedRouting(before_build).snapshot()
    after = CompressedRouting(after_build).snapshot()

    state = routing_state(before, graph.nodes)
    changed = churn(before, after, graph.nodes)
    locality = failure_locality(before_build, after_build)

    assert "forwarding_entry" in state["by_category"]
    assert "local_topology_node" in state["by_category"]
    assert changed["changed_objects"] >= changed["changed_forwarding_objects"]
    assert locality["recomputed_scope_count"] > 0


def test_s0_absorbs_internal_change_when_published_summary_is_unchanged() -> None:
    graph = mesh2d(4, 4)
    tree_control = BalancedConnectedDecomposition(4).decompose(graph)
    builder = SummaryBuilder(tree_control, graph, SummaryConfig("s0"))
    before = builder.build(graph)
    internal = next(event for event in single_link_events(graph, tree_control) if event.classification == "internal")
    after = builder.build(internal.apply(graph))

    locality = failure_locality(before, after)

    assert locality["changed_published_summary_count"] == 0
    assert locality["reached_root"] is False
