"""Scope and quotient graph tests."""

import pytest

from netsynth.decomposition import BalancedConnectedDecomposition
from netsynth.topology import expander_like, mesh2d, tree


@pytest.mark.parametrize("graph", [tree(31), mesh2d(5, 6), expander_like(30, 3, 7)])
def test_balanced_decomposition_is_laminar_connected_and_complete(graph: object) -> None:
    from netsynth.graph import Graph

    assert isinstance(graph, Graph)
    scope_tree = BalancedConnectedDecomposition(4).decompose(graph)

    scope_tree.validate(graph)
    assert frozenset().union(*(leaf.members for leaf in scope_tree.leaves())) == graph.nodes
    assert all(graph.induced(leaf.members).is_connected() for leaf in scope_tree.leaves())
    assert all(quotient.graph.is_connected() for quotient in scope_tree.quotients(graph).values())
