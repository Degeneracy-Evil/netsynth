"""Phase-4 hierarchical attachment lookahead tests."""

import pytest

from netsynth.attachments import Lookahead, compile_attachment_forwarding
from netsynth.decomposition import BalancedConnectedDecomposition
from netsynth.forwarding import Locator, LocatorCatalog, compile_scoped_potentials, execute_forwarding
from netsynth.graph import Edge, Graph
from netsynth.topology import generate


def _weighted(graph: Graph) -> Graph:
    return Graph(
        set(graph.nodes),
        [Edge(edge.left, edge.right, float((index * 7) % 13 + 1)) for index, edge in enumerate(graph.edges)],
    )


@pytest.mark.parametrize("lookahead", [1, 2, 3, "full"])
@pytest.mark.parametrize(
    ("family", "parameters"),
    [
        ("tree", {"node_count": 16}),
        ("mesh2d", {"rows": 4, "columns": 4}),
        ("torus2d", {"rows": 4, "columns": 4}),
        ("erdos_renyi", {"node_count": 16, "probability": 0.2}),
        ("expander_like", {"node_count": 16, "chords_per_node": 3}),
    ],
)
def test_all_lookaheads_deliver_and_remain_prefix_monotone(
    lookahead: Lookahead, family: str, parameters: dict[str, int | float | str]
) -> None:
    graph = _weighted(generate(family, parameters, 7))
    tree = BalancedConnectedDecomposition(4).decompose(graph)
    catalog = LocatorCatalog.from_tree(tree)
    network = compile_attachment_forwarding(graph, graph, tree, catalog, lookahead).network
    for source in graph.nodes:
        for target in graph.nodes:
            if source == target:
                continue
            destination = catalog.by_node[target]
            result = execute_forwarding(network, graph, source, destination, 4 * len(graph.nodes))
            assert result.status == "delivered"
            matched = [_matched_prefix(locator, destination) for locator in result.locators]
            assert matched == sorted(matched)


def test_h1_exactly_reproduces_scoped_potential_routes() -> None:
    graph = generate("mesh2d", {"rows": 4, "columns": 4}, 3)
    tree = BalancedConnectedDecomposition(4).decompose(graph)
    catalog = LocatorCatalog.from_tree(tree)
    phase3 = compile_scoped_potentials(graph, tree, catalog).network
    h1 = compile_attachment_forwarding(graph, graph, tree, catalog, 1).network
    for source in graph.nodes:
        for target in graph.nodes:
            if source != target:
                destination = catalog.by_node[target]
                assert execute_forwarding(phase3, graph, source, destination, 64) == execute_forwarding(
                    h1, graph, source, destination, 64
                )


def test_attachments_equal_child_values_and_use_no_path_planner(monkeypatch: pytest.MonkeyPatch) -> None:
    graph = generate("mesh2d", {"rows": 4, "columns": 4}, 0)
    tree = BalancedConnectedDecomposition(4).decompose(graph)
    catalog = LocatorCatalog.from_tree(tree)

    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("attachment convergence must not call a path planner")

    monkeypatch.setattr(Graph, "shortest_path", forbidden)
    compilation = compile_attachment_forwarding(graph, graph, tree, catalog, "full")
    state = compilation.network.state.objects
    for (owner, category, parent_scope, _identifier), record in state.items():
        if category != "attachment_advertisement":
            continue
        child_scope, key, _locator, advertised = record.value
        assert isinstance(child_scope, str)
        assert advertised == state[(owner, "potential_record", child_scope, str(key))].value[1]
        assert child_scope.startswith(parent_scope)


def test_eligible_hops_descend_and_full_bounds_limited_and_flat() -> None:
    graph = _weighted(generate("expander_like", {"node_count": 20, "chords_per_node": 3}, 5))
    tree = BalancedConnectedDecomposition(4).decompose(graph)
    catalog = LocatorCatalog.from_tree(tree)
    compilations = {
        lookahead: compile_attachment_forwarding(graph, graph, tree, catalog, lookahead)
        for lookahead in (1, 2, 3, "full")
    }
    node_by_locator = {locator: node for node, locator in catalog.by_node.items()}
    for compilation in compilations.values():
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
    for source in graph.nodes:
        for target in graph.nodes:
            if source == target:
                continue
            destination = catalog.by_node[target]
            costs = {
                lookahead: execute_forwarding(compilation.network, graph, source, destination, 80).cost
                for lookahead, compilation in compilations.items()
            }
            shortest = graph.shortest_path(source, target)
            assert shortest is not None
            assert shortest.cost <= costs["full"] + 1e-12
            assert all(costs["full"] <= costs[lookahead] + 1e-12 for lookahead in (1, 2, 3))


def test_scope_connected_failure_delivers_for_every_lookahead() -> None:
    graph = generate("mesh2d", {"rows": 4, "columns": 4}, 0)
    tree = BalancedConnectedDecomposition(4).decompose(graph)
    catalog = LocatorCatalog.from_tree(tree)
    failed = graph.without(edges=frozenset(((0, 4),)))
    assert all(failed.induced(scope.members).is_connected() for scope in tree.scopes())
    for lookahead in (1, 2, 3, "full"):
        network = compile_attachment_forwarding(failed, graph, tree, catalog, lookahead).network
        statuses = {
            execute_forwarding(network, failed, source, catalog.by_node[target], 64).status
            for source in failed.nodes
            for target in failed.nodes
            if source != target
        }
        assert statuses == {"delivered"}


def _matched_prefix(left: Locator, right: Locator) -> int:
    index = 0
    while (
        index < min(len(left.components), len(right.components)) and left.components[index] == right.components[index]
    ):
        index += 1
    return index
