"""Phase-5 decomposition strategy and metric tests."""

from netsynth.decomposition import (
    BalancedConnectedDecomposition,
    MetricAwareDecomposition,
    PoorConnectedDecomposition,
)
from netsynth.decomposition_metrics import decomposition_quality
from netsynth.phase3 import Phase3Config, run_phase3
from netsynth.topology import generate


def test_metric_oracle_is_deterministic_connected_and_charged_as_construction_work() -> None:
    graph = generate("mesh2d", {"rows": 4, "columns": 4}, 0)
    first = MetricAwareDecomposition(4, candidate_limit=20, seed=9)
    second = MetricAwareDecomposition(4, candidate_limit=20, seed=9)
    left, right = first.decompose(graph), second.decompose(graph)
    assert left == right
    left.validate(graph)
    assert first.parameters["formation_model"] == "centralized_research_oracle_not_deployable"
    assert first.construction_stats == second.construction_stats
    assert first.construction_stats["candidate_splits_evaluated"] > 0
    assert first.construction_stats["shortest_path_computations"] > 0


def test_all_controls_produce_valid_hierarchies_and_tree_scopes_are_isometric() -> None:
    graph = generate("tree", {"node_count": 16}, 3)
    for strategy in (
        BalancedConnectedDecomposition(4),
        MetricAwareDecomposition(4, candidate_limit=16, seed=3),
        PoorConnectedDecomposition(4),
    ):
        tree = strategy.decompose(graph)
        tree.validate(graph)
        quality = decomposition_quality(graph, tree)
        assert quality["aggregate_distortion"]["max"] == 1.0
        assert quality["aggregate_distortion"]["exactly_one_fraction"] == 1.0


def test_phase5_records_decomposition_metrics_and_full_correctness() -> None:
    result = run_phase3(
        Phase3Config(
            "expander_like",
            {"node_count": 12, "chords_per_node": 2},
            seed=4,
            leaf_size=3,
            failure_sample_count=1,
            decomposition="d1",
            d1_candidate_limit=12,
        )
    )
    assert result["schema"]["version"] == "5.0"
    assert result["decomposition_control"]["strategy_id"] == "d1"
    assert result["decomposition_control"]["quality"]["aggregate_distortion"]["count"] > 0
    assert result["strategies"]["attachment_hfull"]["distributed"]["statuses"]["delivered"] == 132
    assert result["strategies"]["attachment_comparison"]["full_below_flat_violations"] == 0


def test_poor_control_is_more_unbalanced_than_d0() -> None:
    graph = generate("mesh2d", {"rows": 4, "columns": 4}, 0)
    d0 = BalancedConnectedDecomposition(4).decompose(graph)
    bad = PoorConnectedDecomposition(4).decompose(graph)
    assert max(len(locator) for locator in _paths(bad)) > max(len(locator) for locator in _paths(d0))


def _paths(tree: object) -> list[tuple[int, ...]]:
    from netsynth.decomposition import ScopeTree
    from netsynth.forwarding import LocatorCatalog

    assert isinstance(tree, ScopeTree)
    return [locator.components for locator in LocatorCatalog.from_tree(tree).by_node.values()]
