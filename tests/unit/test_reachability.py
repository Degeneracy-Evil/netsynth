"""Interface-closed reachability summaries and converged forwarding tests."""

import pytest

from netsynth.decomposition import BalancedConnectedDecomposition
from netsynth.forwarding import LocatorCatalog, compile_forwarding, execute_forwarding
from netsynth.phase3 import Phase3Config, _relabel_structure, run_phase3
from netsynth.scaling import run_scaling
from netsynth.summaries import SummaryBuilder, SummaryConfig
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
def test_r0_delivers_every_connected_static_pair(
    family: str, parameters: dict[str, int | float | str], seed: int
) -> None:
    graph = generate(family, parameters, seed)
    tree = BalancedConnectedDecomposition(4).decompose(graph)
    catalog = LocatorCatalog.from_tree(tree)
    build = SummaryBuilder(tree, graph, SummaryConfig("r0")).build(graph)
    network = compile_forwarding(build, catalog)
    for source in graph.nodes:
        for target in graph.nodes:
            if source != target:
                route = execute_forwarding(network, graph, source, catalog.by_node[target], 4 * len(graph.nodes))
                assert route.status == "delivered"


def test_each_scope_preserves_exact_boundary_connectivity_after_failure() -> None:
    graph = generate("mesh2d", {"rows": 4, "columns": 4}, 0)
    tree = BalancedConnectedDecomposition(3).decompose(graph)
    builder = SummaryBuilder(tree, graph, SummaryConfig("r0"))
    for failed in (graph, graph.without(edges=frozenset(((0, 1),))), graph.without(nodes=frozenset((5,)))):
        build = builder.build(failed)
        for scope in tree.scopes():
            summary = build.views[scope.identifier].summary
            assert set(summary.boundary_nodes) == {
                node
                for edge in graph.edges
                for node in (edge.left, edge.right)
                if node in scope.members and ((edge.left in scope.members) != (edge.right in scope.members))
            }
            for left in summary.boundary_nodes:
                for right in summary.boundary_nodes:
                    physical = failed.induced(scope.members).shortest_path(left, right) is not None
                    abstract = any(
                        left in component and right in component for component in summary.connectivity_components
                    )
                    assert physical == abstract


def test_connected_failure_has_no_false_no_route_and_partition_never_delivers() -> None:
    graph = generate("mesh2d", {"rows": 4, "columns": 4}, 0)
    tree = BalancedConnectedDecomposition(4).decompose(graph)
    catalog = LocatorCatalog.from_tree(tree)
    builder = SummaryBuilder(tree, graph, SummaryConfig("r0"))
    connected = graph.without(edges=frozenset(((0, 4),)))
    network = compile_forwarding(builder.build(connected), catalog)
    for source in connected.nodes:
        for target in connected.nodes:
            if source != target:
                result = execute_forwarding(network, connected, source, catalog.by_node[target], 64)
                assert result.status == "delivered"
    # The fixed hierarchy may cease to be prefix-monotone admissible even while
    # the physical graph stays connected. This is not a missing R0 summary edge.
    detour_only = graph.without(edges=frozenset(((0, 1),)))
    assert detour_only.is_connected()
    assert not detour_only.induced(tree.leaf_for(0).members).is_connected()
    detour_network = compile_forwarding(builder.build(detour_only), catalog)
    assert execute_forwarding(detour_network, detour_only, 0, catalog.by_node[1], 64).status == "no_route"
    physical_tree = generate("tree", {"node_count": 10}, 0)
    scope_tree = BalancedConnectedDecomposition(3).decompose(physical_tree)
    catalog_tree = LocatorCatalog.from_tree(scope_tree)
    partitioned = physical_tree.without(edges=frozenset(((0, 1),)))
    network_tree = compile_forwarding(
        SummaryBuilder(scope_tree, physical_tree, SummaryConfig("r0")).build(partitioned), catalog_tree
    )
    result = execute_forwarding(network_tree, partitioned, 0, catalog_tree.by_node[9], 40)
    assert result.status != "delivered"


def test_fixed_structure_relabel_preserves_reachability_and_scope_structure() -> None:
    graph = generate("expander_like", {"node_count": 16, "chords_per_node": 3}, 9)
    tree = BalancedConnectedDecomposition(4).decompose(graph)
    relabeled_graph, relabeled_tree = _relabel_structure(graph, tree, 77)
    assert len(relabeled_tree.scopes()) == len(tree.scopes())
    assert sorted(len(scope.members) for scope in relabeled_tree.scopes()) == sorted(
        len(scope.members) for scope in tree.scopes()
    )
    for candidate_graph, candidate_tree in ((graph, tree), (relabeled_graph, relabeled_tree)):
        catalog = LocatorCatalog.from_tree(candidate_tree)
        network = compile_forwarding(
            SummaryBuilder(candidate_tree, candidate_graph, SummaryConfig("r0")).build(candidate_graph), catalog
        )
        assert all(
            execute_forwarding(network, candidate_graph, source, catalog.by_node[target], 64).status == "delivered"
            for source in candidate_graph.nodes
            for target in candidate_graph.nodes
            if source != target
        )
    result = run_phase3(
        Phase3Config(
            "expander_like",
            {"node_count": 16, "chords_per_node": 3},
            seed=9,
            leaf_size=4,
            failure_sample_count=0,
            fixed_structure_label_seed=77,
        )
    )
    assert result["strategies"]["r0"]["distributed"]["statuses"]["no_route"] == 0


def test_r0_persistent_summary_state_is_linear_in_boundary_interfaces() -> None:
    graph = generate("expander_like", {"node_count": 20, "chords_per_node": 3}, 3)
    tree = BalancedConnectedDecomposition(4).decompose(graph)
    build = SummaryBuilder(tree, graph, SummaryConfig("r0")).build(graph)
    for view in build.views.values():
        summary = view.summary
        stored_references = sum(len(component) for component in summary.connectivity_components)
        assert stored_references <= len(summary.boundary_nodes)
        assert len(summary.connectivity_components) <= len(summary.boundary_nodes)
        assert not summary.distances
    network = compile_forwarding(build, LocatorCatalog.from_tree(tree))
    categories = {key[1] for key in network.state.objects}
    assert "reachability_boundary" in categories
    assert "reachability_component" in categories
    assert "reachability_interface" in categories


def test_scaling_output_marks_sampling_and_reachability_state() -> None:
    result = run_scaling(sizes=(16, 32), families=("tree", "mesh2d"), seed=3, pair_sample_count=32)
    assert result["schema"]["version"] == "5.0"
    assert len(result["rows"]) == 4
    for row in result["rows"]:
        assert row["pairs"] == {"count": 32, "sampled": True}
        assert row["no_route"] == 0
        assert row["flat_normalized_size_reference"] > 0
        assert row["reachability_summary_state"]["reachability_boundary"]["normalized_size_total"] > 0
        assert row["reachability_summary_state"]["reachability_component"]["normalized_size_total"] > 0
        assert row["reachability_summary_state"]["reachability_interface"]["normalized_size_total"] > 0
        assert row["scoped_potential"]["delivered"] == 32
        assert row["scoped_potential"]["loop"] == 0
        assert all(row["attachment_lookahead"][name]["delivered"] == 32 for name in ("h1", "h2", "h3", "hfull"))
