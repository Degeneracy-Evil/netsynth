"""Controlled physical topology-change events."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any

from netsynth.decomposition import ScopeTree
from netsynth.graph import Graph, Node


@dataclass(frozen=True)
class FailureEvent:
    """A reproducible set of independent physical objects taken down."""

    kind: str
    nodes: frozenset[Node] = frozenset()
    links: frozenset[tuple[Node, Node]] = frozenset()
    classification: str = "unspecified"

    def apply(self, graph: Graph) -> Graph:
        """Create the failed snapshot; recovery is the unchanged original snapshot."""
        return graph.without(nodes=self.nodes, edges=self.links)

    def to_dict(self) -> dict[str, Any]:
        """Return a machine-readable event definition."""
        return {
            "kind": self.kind,
            "nodes": sorted(self.nodes),
            "links": [list(link) for link in sorted(self.links)],
            "classification": self.classification,
        }


def single_link_events(graph: Graph, tree: ScopeTree) -> list[FailureEvent]:
    """Enumerate link-down events and label finest-scope boundary crossings."""
    leaf_by_node = {node: tree.leaf_for(node).identifier for node in graph.nodes}
    return [
        FailureEvent(
            "single_link_down",
            links=frozenset((edge.key,)),
            classification="internal" if leaf_by_node[edge.left] == leaf_by_node[edge.right] else "boundary",
        )
        for edge in graph.edges
    ]


def single_node_events(graph: Graph) -> list[FailureEvent]:
    """Enumerate single forwarding-node failures."""
    return [FailureEvent("single_node_down", nodes=frozenset((node,))) for node in sorted(graph.nodes)]


def random_link_set_event(graph: Graph, count: int, seed: int) -> FailureEvent:
    """Select a deterministic independent set of physical links."""
    if count < 1 or count > len(graph.edges):
        raise ValueError("random failure count must fit the graph")
    chosen = random.Random(seed).sample(list(graph.edges), count)
    return FailureEvent("random_link_set_down", links=frozenset(edge.key for edge in chosen))


def sample_events(events: list[FailureEvent], count: int | None, seed: int) -> list[FailureEvent]:
    """Sample events reproducibly or retain the exhaustive list."""
    if count is None or count >= len(events):
        return events
    return random.Random(seed).sample(events, count)
