"""Metric-definition tests."""

from netsynth.decomposition import BalancedConnectedDecomposition
from netsynth.failures import single_link_events
from netsynth.metrics import churn, failure_locality, path_stretch
from netsynth.routing import CompressedRouting, FlatRouting
from netsynth.topology import tree


def test_flat_self_comparison_has_unit_stretch() -> None:
    graph = tree(8)
    flat = FlatRouting()
    result = path_stretch(graph, flat, flat, [(0, 7), (3, 5)], sampled=True)
    assert result["exactly_one_fraction"] == 1.0
    assert result["sampled"] is True


def test_churn_and_failure_locality_are_explicit() -> None:
    graph = tree(15)
    scopes = BalancedConnectedDecomposition(3).decompose(graph)
    routing = CompressedRouting(scopes)
    event = single_link_events(graph, scopes)[0]
    failed = event.apply(graph)

    changed = churn(routing.snapshot(graph), routing.snapshot(failed), graph.nodes)
    locality = failure_locality(graph, failed, scopes)

    assert changed["changed_objects"] > 0
    assert locality["changed_scope_count"] > 0
    assert locality["reached_scope_count"] >= locality["changed_scope_count"]
    assert isinstance(locality["reached_root"], bool)
