"""Physical topology generators and JSON importer."""

from __future__ import annotations

import json
import math
import random
from pathlib import Path
from typing import Any

from netsynth.graph import Edge, Graph


def tree(node_count: int, branching: int = 2) -> Graph:
    """Generate a breadth-first regular tree."""
    _require_nodes(node_count)
    if branching < 1:
        raise ValueError("branching must be positive")
    return Graph(set(range(node_count)), [Edge((node - 1) // branching, node) for node in range(1, node_count)])


def mesh2d(rows: int, columns: int, *, torus: bool = False) -> Graph:
    """Generate a rectangular mesh or wrap-around torus."""
    if rows < 1 or columns < 1 or rows * columns < 2:
        raise ValueError("mesh must contain at least two nodes")
    pairs: set[tuple[int, int]] = set()
    for row in range(rows):
        for column in range(columns):
            node = row * columns + column
            candidates = [(row, column + 1), (row + 1, column)]
            if torus:
                candidates = [(row, (column + 1) % columns), ((row + 1) % rows, column)]
            for other_row, other_column in candidates:
                if other_row < rows and other_column < columns:
                    other = other_row * columns + other_column
                    if node != other:
                        pairs.add((min(node, other), max(node, other)))
    return Graph(set(range(rows * columns)), [Edge(*pair) for pair in sorted(pairs)])


def erdos_renyi(node_count: int, probability: float, seed: int) -> Graph:
    """Generate a connected Erdos-Renyi-like graph using a random tree backbone."""
    _require_nodes(node_count)
    if not 0.0 <= probability <= 1.0:
        raise ValueError("probability must be between zero and one")
    rng = random.Random(seed)
    pairs = {(rng.randrange(node), node) for node in range(1, node_count)}
    for left in range(node_count):
        for right in range(left + 1, node_count):
            if rng.random() < probability:
                pairs.add((left, right))
    return Graph(set(range(node_count)), [Edge(*pair) for pair in sorted(pairs)])


def small_world(node_count: int, neighbor_count: int, rewire_probability: float, seed: int) -> Graph:
    """Generate a ring lattice with reproducible shortcut rewiring."""
    _require_nodes(node_count)
    if neighbor_count < 2 or neighbor_count >= node_count or neighbor_count % 2:
        raise ValueError("neighbor_count must be even and between 2 and node_count")
    if not 0.0 <= rewire_probability <= 1.0:
        raise ValueError("rewire_probability must be between zero and one")
    rng = random.Random(seed)
    pairs: set[tuple[int, int]] = set()
    for node in range(node_count):
        for offset in range(1, neighbor_count // 2 + 1):
            other = (node + offset) % node_count
            if rng.random() < rewire_probability:
                choices = [
                    candidate
                    for candidate in range(node_count)
                    if candidate != node and tuple(sorted((node, candidate))) not in pairs
                ]
                if choices:
                    other = rng.choice(choices)
            pairs.add((min(node, other), max(node, other)))
    # Retain a minimal ring so aggressive rewiring never makes a requested experiment invalid.
    pairs.update((node, node + 1) for node in range(node_count - 1))
    pairs.add((0, node_count - 1))
    return Graph(set(range(node_count)), [Edge(*pair) for pair in sorted(pairs)])


def random_geometric(node_count: int, radius: float, seed: int) -> Graph:
    """Generate a locality graph, adding only nearest-component bridges for connectivity."""
    _require_nodes(node_count)
    if radius <= 0:
        raise ValueError("radius must be positive")
    rng = random.Random(seed)
    positions = [(rng.random(), rng.random()) for _ in range(node_count)]
    pairs: set[tuple[int, int]] = set()
    distances: list[tuple[float, int, int]] = []
    for left in range(node_count):
        for right in range(left + 1, node_count):
            distance = math.dist(positions[left], positions[right])
            distances.append((distance, left, right))
            if distance <= radius:
                pairs.add((left, right))
    # Kruskal bridges preserve the intended locality while making experiment failures meaningful.
    parent = list(range(node_count))

    def find(node: int) -> int:
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    for _distance, left, right in sorted(distances):
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[right_root] = left_root
            pairs.add((left, right))
    edges = [Edge(left, right, cost=math.dist(positions[left], positions[right])) for left, right in sorted(pairs)]
    return Graph(set(range(node_count)), edges)


def clos(leaf_count: int, spine_count: int, endpoints_per_leaf: int) -> Graph:
    """Generate a simple two-stage Clos-like physical graph."""
    if min(leaf_count, spine_count, endpoints_per_leaf) < 1:
        raise ValueError("Clos dimensions must be positive")
    spine_nodes = range(spine_count)
    leaf_nodes = range(spine_count, spine_count + leaf_count)
    first_endpoint = spine_count + leaf_count
    pairs = {(spine, leaf) for spine in spine_nodes for leaf in leaf_nodes}
    for leaf_index, leaf in enumerate(leaf_nodes):
        for offset in range(endpoints_per_leaf):
            pairs.add((leaf, first_endpoint + leaf_index * endpoints_per_leaf + offset))
    count = first_endpoint + leaf_count * endpoints_per_leaf
    return Graph(set(range(count)), [Edge(*pair) for pair in sorted(pairs)])


def expander_like(node_count: int, chords_per_node: int, seed: int) -> Graph:
    """Generate a high-conductance control graph from a ring plus random chords."""
    _require_nodes(node_count)
    if chords_per_node < 1:
        raise ValueError("chords_per_node must be positive")
    rng = random.Random(seed)
    pairs = {tuple(sorted((node, (node + 1) % node_count))) for node in range(node_count)}
    target = node_count * chords_per_node // 2
    attempts = 0
    while len(pairs) < node_count + target and attempts < node_count * node_count * 10:
        attempts += 1
        left, right = rng.sample(range(node_count), 2)
        pairs.add(tuple(sorted((left, right))))
    return Graph(set(range(node_count)), [Edge(*pair) for pair in sorted(pairs)])


def from_json(path: Path) -> Graph:
    """Import the documented graph shape from JSON."""
    raw: Any = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("nodes"), list) or not isinstance(raw.get("links"), list):
        raise ValueError("topology JSON requires nodes and links lists")
    nodes = {int(node) for node in raw["nodes"]}
    edges = [
        Edge(int(link["left"]), int(link["right"]), float(link.get("cost", 1.0)), float(link.get("capacity", 1.0)))
        for link in raw["links"]
        if isinstance(link, dict)
    ]
    return Graph(nodes, edges)


def generate(family: str, parameters: dict[str, int | float | str], seed: int) -> Graph:
    """Generate one configured topology family."""
    if family == "tree":
        return tree(int(parameters["node_count"]), int(parameters.get("branching", 2)))
    if family in {"mesh2d", "torus2d"}:
        return mesh2d(int(parameters["rows"]), int(parameters["columns"]), torus=family == "torus2d")
    if family == "erdos_renyi":
        return erdos_renyi(int(parameters["node_count"]), float(parameters.get("probability", 0.1)), seed)
    if family == "small_world":
        return small_world(
            int(parameters["node_count"]),
            int(parameters.get("neighbor_count", 4)),
            float(parameters.get("rewire_probability", 0.1)),
            seed,
        )
    if family == "random_geometric":
        return random_geometric(int(parameters["node_count"]), float(parameters.get("radius", 0.2)), seed)
    if family == "clos":
        return clos(
            int(parameters["leaf_count"]),
            int(parameters["spine_count"]),
            int(parameters["endpoints_per_leaf"]),
        )
    if family == "expander_like":
        return expander_like(int(parameters["node_count"]), int(parameters.get("chords_per_node", 3)), seed)
    if family == "json":
        return from_json(Path(str(parameters["path"])))
    raise ValueError(f"unknown topology family: {family}")


def _require_nodes(node_count: int) -> None:
    if node_count < 2:
        raise ValueError("topology must contain at least two nodes")
