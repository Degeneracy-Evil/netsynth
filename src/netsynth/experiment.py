"""Reproducible experiment runner and machine-readable result assembly."""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from netsynth.decomposition import BalancedConnectedDecomposition, ScopeTree
from netsynth.failures import FailureEvent, random_link_set_event, sample_events, single_link_events, single_node_events
from netsynth.graph import Graph, Node
from netsynth.metrics import churn, distribution, failure_locality, path_stretch, routing_state
from netsynth.routing import CompressedRouting, FlatRouting, RoutingSnapshot
from netsynth.topology import generate

METRIC_SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class ExperimentConfig:
    """All inputs required to reproduce one experiment."""

    topology_family: str
    topology_parameters: dict[str, int | float | str]
    seed: int = 0
    leaf_size: int = 8
    pair_sample_count: int | None = None
    failure_sample_count: int | None = 16
    random_failure_link_count: int = 2
    routing_parameters: dict[str, str] = field(default_factory=lambda: {"quotient_edge": "minimum_crossing_link"})


def run_experiment(config: ExperimentConfig) -> dict[str, Any]:
    """Run baseline/compressed routing and failures on exactly one physical graph."""
    graph = generate(config.topology_family, config.topology_parameters, config.seed)
    decomposition = BalancedConnectedDecomposition(config.leaf_size)
    tree = decomposition.decompose(graph)
    flat = FlatRouting()
    compressed = CompressedRouting(tree)
    pairs, pairs_sampled = _pairs(graph, config.pair_sample_count, config.seed + 1)
    flat_before = flat.snapshot(graph)
    compressed_before = compressed.snapshot(graph)
    events = [*single_link_events(graph, tree), *single_node_events(graph)]
    if graph.edges and config.random_failure_link_count <= len(graph.edges):
        events.append(random_link_set_event(graph, config.random_failure_link_count, config.seed + 2))
    selected_events = sample_events(events, config.failure_sample_count, config.seed + 3)
    event_results = [
        _run_failure(graph, event, tree, flat, compressed, flat_before, compressed_before) for event in selected_events
    ]
    return {
        "schema": {"name": "netsynth.phase1", "version": METRIC_SCHEMA_VERSION},
        "topology": _topology_metadata(config, graph),
        "decomposition": {"parameters": decomposition.parameters, **tree.describe(graph)},
        "routing": {
            "baseline": {"name": flat.name, "parameters": {}},
            "compressed": {"name": compressed.name, "parameters": config.routing_parameters},
        },
        "sampling": {
            "pairs_sampled": pairs_sampled,
            "pair_count": len(pairs),
            "failures_sampled": len(selected_events) < len(events),
            "failure_count": len(selected_events),
            "available_failure_count": len(events),
        },
        "metrics": {
            "routing_state": {
                "flat": routing_state(flat_before, graph.nodes),
                "compressed": routing_state(compressed_before, graph.nodes),
            },
            "path_stretch": path_stretch(graph, flat, compressed, pairs, sampled=pairs_sampled),
            "failure_experiments": event_results,
            "failure_distributions": _failure_distributions(event_results),
        },
        "definitions": {
            "state_entry": "one node-owned destination or aggregate next-scope/cost object",
            "churn": "changed state-object values; simulator computation is excluded",
            "scope_summary": "external crossing links plus shortest distances among stable boundary nodes",
            "recovery": "restoring an event returns the original snapshot and has symmetric object differences",
        },
    }


def _pairs(graph: Graph, count: int | None, seed: int) -> tuple[list[tuple[Node, Node]], bool]:
    pairs = [(source, target) for source in sorted(graph.nodes) for target in sorted(graph.nodes) if source != target]
    if count is None or count >= len(pairs):
        return pairs, False
    return random.Random(seed).sample(pairs, count), True


def _topology_metadata(config: ExperimentConfig, graph: Graph) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "family": config.topology_family,
        "parameters": config.topology_parameters,
        "seed": config.seed,
        "node_count": len(graph.nodes),
        "link_count": len(graph.edges),
    }
    if config.topology_family == "json":
        content = Path(str(config.topology_parameters["path"])).read_bytes()
        metadata["input_sha256"] = hashlib.sha256(content).hexdigest()
    return metadata


def _run_failure(
    graph: Graph,
    event: FailureEvent,
    tree: ScopeTree,
    flat: FlatRouting,
    compressed: CompressedRouting,
    flat_before: RoutingSnapshot,
    compressed_before: RoutingSnapshot,
) -> dict[str, Any]:
    failed = event.apply(graph)
    flat_after = flat.snapshot(failed)
    compressed_after = compressed.snapshot(failed)
    return {
        "event": event.to_dict(),
        "remaining_node_count": len(failed.nodes),
        "remaining_link_count": len(failed.edges),
        "flat_churn": churn(flat_before, flat_after, graph.nodes),
        "compressed_churn": churn(compressed_before, compressed_after, graph.nodes),
        "recovery": {
            "kind": event.kind.replace("_down", "_up"),
            "flat_churn": churn(flat_after, flat_before, graph.nodes),
            "compressed_churn": churn(compressed_after, compressed_before, graph.nodes),
        },
        "failure_locality": failure_locality(graph, failed, tree),
    }


def _failure_distributions(results: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "flat_changed_objects": distribution(
            (float(result["flat_churn"]["changed_objects"]) for result in results), (50, 95, 99)
        ),
        "compressed_changed_objects": distribution(
            (float(result["compressed_churn"]["changed_objects"]) for result in results), (50, 95, 99)
        ),
        "compressed_changed_node_fraction": distribution(
            (float(result["compressed_churn"]["changed_node_fraction"]) for result in results), (50, 95, 99)
        ),
        "changed_scope_count": distribution(
            (float(result["failure_locality"]["changed_scope_count"]) for result in results), (50, 95, 99)
        ),
        "highest_level_from_leaf": distribution(
            (
                float(level)
                for result in results
                if (level := result["failure_locality"]["highest_level_from_leaf"]) is not None
            ),
            (50, 95, 99),
        ),
        "reached_root_fraction": (
            sum(bool(result["failure_locality"]["reached_root"]) for result in results) / len(results)
            if results
            else None
        ),
        "by_classification": _by_classification(results),
    }


def _by_classification(results: list[dict[str, Any]]) -> dict[str, Any]:
    labels = sorted({str(result["event"]["classification"]) for result in results})
    return {
        label: {
            "event_count": len(group),
            "changed_scope_count": distribution(
                (float(result["failure_locality"]["changed_scope_count"]) for result in group), (50, 95, 99)
            ),
        }
        for label in labels
        if (group := [result for result in results if result["event"]["classification"] == label])
    }
