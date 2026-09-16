"""Phase-3 knowledge-boundary and distributed execution tests."""

from types import MappingProxyType

from netsynth.decomposition import Scope, ScopeTree
from netsynth.forwarding import (
    ForwardingKnowledge,
    ForwardingNetwork,
    Locator,
    LocatorCatalog,
    compile_forwarding,
    execute_forwarding,
)
from netsynth.graph import Edge, Graph
from netsynth.routing import CompressedRouting, RoutingSnapshot, validate_path
from netsynth.summaries import SummaryBuilder, SummaryConfig
from netsynth.topology import tree


def test_tree_forwarding_uses_only_compiled_local_knowledge() -> None:
    graph = tree(12)
    from netsynth.decomposition import BalancedConnectedDecomposition

    scopes = BalancedConnectedDecomposition(3).decompose(graph)
    catalog = LocatorCatalog.from_tree(scopes)
    build = SummaryBuilder(scopes, graph, SummaryConfig("s3")).build(graph)
    network = compile_forwarding(build, catalog)
    for source in graph.nodes:
        for target in graph.nodes:
            if source != target:
                result = execute_forwarding(network, graph, source, catalog.by_node[target], 48)
                assert result.status == "delivered"
                assert result.hops > 0
    knowledge = next(iter(network.knowledge.values()))
    assert not hasattr(knowledge, "graph")
    assert not hasattr(knowledge, "tree")
    assert all(isinstance(reference, (Locator, tuple)) for reference in knowledge.fib)
    assert all(isinstance(neighbor, Locator) for neighbor in knowledge.neighbors)
    for owner, state in network.knowledge.items():
        for target_locator in catalog.by_node.values():
            if target_locator == owner:
                continue
            selected = state.next_hop(target_locator, 48)
            if selected is None:
                continue
            before = next(
                (
                    index
                    for index, (left, right) in enumerate(
                        zip(owner.components, target_locator.components, strict=False)
                    )
                    if left != right
                ),
                min(len(owner.components), len(target_locator.components)),
            )
            after = next(
                (
                    index
                    for index, (left, right) in enumerate(
                        zip(selected.components, target_locator.components, strict=False)
                    )
                    if left != right
                ),
                min(len(selected.components), len(target_locator.components)),
            )
            assert after >= before


def test_remote_leaf_detail_is_absent_and_hidden_attachment_is_indistinguishable() -> None:
    scopes = ScopeTree(
        Scope("root", frozenset({0, 1, 2, 3}), (Scope("left", frozenset({0})), Scope("right", frozenset({1, 2, 3}))))
    )
    base = [Edge(0, 1), Edge(0, 2), Edge(1, 2)]
    near_left = Graph({0, 1, 2, 3}, [*base, Edge(1, 3)])
    near_right = Graph({0, 1, 2, 3}, [*base, Edge(2, 3)])
    catalog = LocatorCatalog.from_tree(scopes)
    left_build = SummaryBuilder(scopes, near_left, SummaryConfig("s3")).build(near_left)
    right_build = SummaryBuilder(scopes, near_left, SummaryConfig("s3")).build(near_right)
    assert left_build.views["right"].summary == right_build.views["right"].summary
    left_network = compile_forwarding(left_build, catalog)
    right_network = compile_forwarding(right_build, catalog)
    owner = catalog.by_node[0]
    target = catalog.by_node[3]
    assert left_network.knowledge[owner].next_hop(target, 16) == right_network.knowledge[owner].next_hop(target, 16)
    assert left_network.knowledge[owner].local_members == frozenset({owner})
    assert target not in left_network.knowledge[owner].local_members
    assert all(
        key[2] != "right" for key in left_network.state.objects if key[0] == 0 and key[1].startswith("local_topology_")
    )


def test_oracle_is_separate_and_physically_valid() -> None:
    graph = tree(8)
    from netsynth.decomposition import BalancedConnectedDecomposition

    scopes = BalancedConnectedDecomposition(2).decompose(graph)
    oracle = CompressedRouting(SummaryBuilder(scopes, graph, SummaryConfig("s3")).build(graph))
    path = oracle.route(0, 7)
    assert path is not None and validate_path(graph, path, 0, 7)
    assert oracle.name == "s3"


def test_loop_and_hop_budget_are_exposed_without_fallback() -> None:
    graph = Graph({0, 1}, [Edge(0, 1)])
    a, b, unreachable = Locator((0,), 0), Locator((1,), 0), Locator((2,), 0)
    knowledge = {
        a: ForwardingKnowledge(a, MappingProxyType({b: 1.0}), MappingProxyType({(2,): b}), frozenset({a})),
        b: ForwardingKnowledge(b, MappingProxyType({a: 1.0}), MappingProxyType({(2,): a}), frozenset({b})),
    }
    network = ForwardingNetwork(MappingProxyType(knowledge), RoutingSnapshot({}), LocatorCatalog({0: a, 1: b}))
    assert execute_forwarding(network, graph, 0, unreachable, 4).status == "loop"
    assert execute_forwarding(network, graph, 0, unreachable, 1).status == "hop_budget_exhausted"
    assert execute_forwarding(network, graph, 0, unreachable, 0).status == "hop_budget_exhausted"
    empty = ForwardingKnowledge(a, MappingProxyType({b: 1.0}), MappingProxyType({}), frozenset({a}))
    no_route = ForwardingNetwork(MappingProxyType({a: empty}), RoutingSnapshot({}), LocatorCatalog({0: a, 1: b}))
    assert execute_forwarding(no_route, graph, 0, b, 4).status == "no_route"


def test_nonadjacent_compiled_hop_is_reported_as_invalid() -> None:
    graph = Graph({0, 1, 2}, [Edge(0, 1), Edge(1, 2)])
    a, b, c = Locator((0,), 0), Locator((1,), 0), Locator((2,), 0)
    invalid = ForwardingKnowledge(a, MappingProxyType({c: 1.0}), MappingProxyType({(1,): c}), frozenset({a}))
    network = ForwardingNetwork(MappingProxyType({a: invalid}), RoutingSnapshot({}), LocatorCatalog({0: a, 1: b, 2: c}))
    assert execute_forwarding(network, graph, 0, b, 4).status == "invalid_next_hop"
