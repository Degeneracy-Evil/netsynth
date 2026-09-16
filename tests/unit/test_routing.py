"""Information-budgeted route correctness tests."""

import pytest

from netsynth.decomposition import BalancedConnectedDecomposition
from netsynth.routing import CompressedRouting, FlatRouting, validate_path
from netsynth.summaries import SummaryBuilder, SummaryConfig
from netsynth.topology import erdos_renyi, mesh2d, tree


@pytest.mark.parametrize("graph", [tree(20), mesh2d(4, 5), erdos_renyi(20, 0.15, 4)])
@pytest.mark.parametrize(
    "config",
    [SummaryConfig("s0"), SummaryConfig("s1"), SummaryConfig("s2", landmark_count=2), SummaryConfig("s3")],
)
def test_every_strategy_returns_only_valid_physical_routes(graph: object, config: SummaryConfig) -> None:
    from netsynth.graph import Graph

    assert isinstance(graph, Graph)
    tree_control = BalancedConnectedDecomposition(4).decompose(graph)
    build = SummaryBuilder(tree_control, graph, config).build(graph)
    routing = CompressedRouting(build)
    for source in graph.nodes:
        for target in graph.nodes:
            if source == target:
                continue
            path = routing.route(source, target)
            assert path is not None
            assert validate_path(graph, path, source, target)


def test_s3_recovers_flat_shortest_paths() -> None:
    graph = mesh2d(4, 5)
    tree_control = BalancedConnectedDecomposition(3).decompose(graph)
    build = SummaryBuilder(tree_control, graph, SummaryConfig("s3")).build(graph)
    flat = FlatRouting(graph)
    compressed = CompressedRouting(build)

    for source in graph.nodes:
        for target in graph.nodes:
            if source != target:
                flat_path = flat.route(source, target)
                compressed_path = compressed.route(source, target)
                assert flat_path is not None
                assert compressed_path is not None
                assert compressed_path.cost == flat_path.cost


def test_state_charges_control_knowledge_and_s3_costs_more_than_s0() -> None:
    graph = mesh2d(5, 5)
    tree_control = BalancedConnectedDecomposition(4).decompose(graph)
    s0 = CompressedRouting(SummaryBuilder(tree_control, graph, SummaryConfig("s0")).build(graph)).snapshot()
    s3 = CompressedRouting(SummaryBuilder(tree_control, graph, SummaryConfig("s3")).build(graph)).snapshot()

    assert len(s3.objects) > len(s0.objects)
    assert any(key[1] == "boundary_distance" for key in s3.objects)
    assert any(key[1] == "crossing_link" for key in s0.objects)
