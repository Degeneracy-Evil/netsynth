"""Bottom-up summary construction invariants."""

from netsynth.decomposition import BalancedConnectedDecomposition
from netsynth.summaries import SummaryBuilder, SummaryConfig
from netsynth.topology import mesh2d


def test_non_leaf_inputs_are_exactly_child_summaries_and_declared_crossings() -> None:
    graph = mesh2d(4, 5)
    tree_control = BalancedConnectedDecomposition(3).decompose(graph)
    build = SummaryBuilder(tree_control, graph, SummaryConfig("s3")).build(graph)

    for scope in tree_control.scopes():
        if scope.is_leaf:
            continue
        view = build.views[scope.identifier]
        expected = (
            tuple((child.identifier, build.views[child.identifier].summary.signature) for child in scope.children),
            tuple((record.identifier, record.value) for record in view.crossings),
        )
        assert view.input_signature == expected


def test_summary_budgets_expose_monotonic_distance_information() -> None:
    graph = mesh2d(5, 5)
    tree_control = BalancedConnectedDecomposition(4).decompose(graph)
    totals = {}
    for config in (SummaryConfig("s0"), SummaryConfig("s2", landmark_count=1), SummaryConfig("s3")):
        build = SummaryBuilder(tree_control, graph, config).build(graph)
        totals[config.name] = sum(len(view.summary.distances) for view in build.views.values())

    assert totals["s0"] < totals["s2_k1"] <= totals["s3"]
