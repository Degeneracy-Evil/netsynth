"""Scoped neighbor-potential correctness tests."""

import pytest

from netsynth.decomposition import BalancedConnectedDecomposition
from netsynth.forwarding import Locator, LocatorCatalog, compile_scoped_potentials, execute_forwarding
from netsynth.graph import Graph
from netsynth.phase3 import Phase3Config, _relabel_structure
from netsynth.topology import generate


@pytest.mark.parametrize(
    ("family", "parameters"),
    [
        ("tree", {"node_count": 20}),
        ("mesh2d", {"rows": 4, "columns": 5}),
        ("torus2d", {"rows": 4, "columns": 5}),
        ("erdos_renyi", {"node_count": 20, "probability": 0.16}),
        ("expander_like", {"node_count": 20, "chords_per_node": 3}),
    ],
)
@pytest.mark.parametrize("seed", [1, 3, 7])
def test_scoped_potential_delivers_all_static_pairs_without_loops(
    family: str, parameters: dict[str, int | float | str], seed: int
) -> None:
    graph = generate(family, parameters, seed)
    tree = BalancedConnectedDecomposition(4).decompose(graph)
    catalog = LocatorCatalog.from_tree(tree)
    compilation = compile_scoped_potentials(graph, tree, catalog)
    for source in graph.nodes:
        for target in graph.nodes:
            if source == target:
                continue
            result = execute_forwarding(
                compilation.network, graph, source, catalog.by_node[target], 4 * len(graph.nodes)
            )
            assert result.status == "delivered"
            assert len(set(result.locators)) == len(result.locators)
    for knowledge in compilation.network.knowledge.values():
        assert knowledge.eligible is not None
        for hops in knowledge.eligible.values():
            assert all(hop in knowledge.neighbors for hop in hops)


def test_compilation_uses_no_shortest_path_or_r0(monkeypatch: pytest.MonkeyPatch) -> None:
    graph = generate("mesh2d", {"rows": 4, "columns": 4}, 0)
    tree = BalancedConnectedDecomposition(4).decompose(graph)
    catalog = LocatorCatalog.from_tree(tree)

    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("potential convergence must not call a path planner")

    monkeypatch.setattr(Graph, "shortest_path", forbidden)
    compilation = compile_scoped_potentials(graph, tree, catalog)
    assert compilation.rounds
    assert all(value >= 0 for value in compilation.rounds.values())


def test_every_eligible_hop_strictly_descends_the_same_scoped_potential() -> None:
    graph = generate("torus2d", {"rows": 4, "columns": 4}, 2)
    tree = BalancedConnectedDecomposition(4).decompose(graph)
    catalog = LocatorCatalog.from_tree(tree)
    compilation = compile_scoped_potentials(graph, tree, catalog)
    node_by_locator = {locator: node for node, locator in catalog.by_node.items()}
    potentials = {
        (owner, scope, identifier): record.value[1]
        for (owner, category, scope, identifier), record in compilation.network.state.objects.items()
        if category == "potential_record"
    }
    for (owner, category, scope, _identifier), record in compilation.network.state.objects.items():
        if category != "eligible_next_hop":
            continue
        key, hop = record.value
        assert isinstance(hop, Locator)
        neighbor_value = potentials[(node_by_locator[hop], scope, str(key))]
        owner_value = potentials[(owner, scope, str(key))]
        assert isinstance(neighbor_value, float)
        assert isinstance(owner_value, float)
        assert neighbor_value < owner_value
        assert graph.edge(owner, node_by_locator[hop]) is not None


def test_scope_connected_failure_and_fixed_structure_relabel_preserve_delivery() -> None:
    graph = generate("mesh2d", {"rows": 4, "columns": 4}, 0)
    tree = BalancedConnectedDecomposition(4).decompose(graph)
    failed = graph.without(edges=frozenset(((0, 4),)))
    assert all(failed.induced(scope.members).is_connected() for scope in tree.scopes())
    relabeled_graph, relabeled_tree = _relabel_structure(failed, tree, 77)
    for candidate, hierarchy in ((failed, tree), (relabeled_graph, relabeled_tree)):
        catalog = LocatorCatalog.from_tree(hierarchy)
        network = compile_scoped_potentials(candidate, hierarchy, catalog).network
        outcomes = [
            execute_forwarding(network, candidate, source, catalog.by_node[target], 64).status
            for source in candidate.nodes
            for target in candidate.nodes
            if source != target
        ]
        assert set(outcomes) == {"delivered"}


def test_config_retains_phase_3_2_controls() -> None:
    assert Phase3Config("tree", {"node_count": 4}).fixed_structure_label_seed is None
