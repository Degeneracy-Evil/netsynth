"""Physical graph tests."""

import json
from pathlib import Path

from netsynth.graph import Edge, Graph
from netsynth.topology import generate


def test_weighted_shortest_path_and_failure_snapshot() -> None:
    graph = Graph({0, 1, 2}, [Edge(0, 1, 5.0, 7.0), Edge(0, 2), Edge(1, 2)])

    path = graph.shortest_path(0, 1)

    assert path is not None
    assert path.nodes == (0, 2, 1)
    assert path.cost == 2.0
    assert graph.without(edges=frozenset(((1, 2),))).shortest_path(0, 1) is not None
    assert graph.without(nodes=frozenset((2,))).nodes == frozenset((0, 1))


def test_edge_normalizes_endpoints_without_corrupting_them() -> None:
    edge = Edge(9, 2)
    assert edge.key == (2, 9)


def test_json_topology_import_preserves_link_metadata(tmp_path: Path) -> None:
    path = tmp_path / "graph.json"
    path.write_text(
        json.dumps({"nodes": [0, 1], "links": [{"left": 0, "right": 1, "cost": 2.5, "capacity": 9.0}]}),
        encoding="utf-8",
    )

    graph = generate("json", {"path": str(path)}, seed=123)

    assert graph.edges == (Edge(0, 1, 2.5, 9.0),)
