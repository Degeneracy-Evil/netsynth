"""Flat and compressed route correctness tests."""

import pytest

from netsynth.decomposition import BalancedConnectedDecomposition
from netsynth.routing import CompressedRouting, FlatRouting, validate_path
from netsynth.topology import erdos_renyi, mesh2d, tree


@pytest.mark.parametrize("graph", [tree(20), mesh2d(4, 5), erdos_renyi(20, 0.15, 4)])
def test_compressed_routes_are_valid_for_all_pairs(graph: object) -> None:
    from netsynth.graph import Graph

    assert isinstance(graph, Graph)
    scopes = BalancedConnectedDecomposition(4).decompose(graph)
    routing = CompressedRouting(scopes)
    for source in graph.nodes:
        for target in graph.nodes:
            if source == target:
                continue
            path = routing.route(graph, source, target)
            assert path is not None
            assert validate_path(graph, path, source, target)


def test_compressed_state_is_smaller_on_tree() -> None:
    graph = tree(63)
    scopes = BalancedConnectedDecomposition(4).decompose(graph)
    flat = FlatRouting().snapshot(graph)
    compressed = CompressedRouting(scopes).snapshot(graph)

    assert len(compressed.entries) < len(flat.entries)
