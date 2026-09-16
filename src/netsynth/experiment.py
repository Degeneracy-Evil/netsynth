"""Reproducible Phase-2 information-budget experiment matrix."""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from netsynth.decomposition import BalancedConnectedDecomposition, ScopeTree
from netsynth.failures import FailureEvent, random_link_set_event, sample_events, single_link_events, single_node_events
from netsynth.graph import Graph, Node
from netsynth.metrics import churn, distribution, failure_locality, path_quality, routing_state
from netsynth.routing import CompressedRouting, FlatRouting, RoutingSnapshot
from netsynth.summaries import SummaryBuild, SummaryBuilder, SummaryConfig
from netsynth.topology import generate

METRIC_SCHEMA_VERSION = "2.0"


@dataclass(frozen=True)
class ExperimentConfig:
    """All inputs required to reproduce one fixed-topology strategy matrix."""

    topology_family: str
    topology_parameters: dict[str, int | float | str]
    seed: int = 0
    leaf_size: int = 8
    pair_sample_count: int | None = None
    failure_sample_count: int | None = 16
    random_failure_link_count: int = 2
    s1_bundle_representatives: int = 2
    s2_landmark_counts: tuple[int, ...] = (1, 2, 4)


@dataclass(frozen=True)
class _StrategyRun:
    config: SummaryConfig
    build: SummaryBuild
    routing: CompressedRouting
    state: RoutingSnapshot


def run_experiment(config: ExperimentConfig) -> dict[str, Any]:
    """Run Flat/S0/S1/S2/S3 on identical graph, decomposition, pairs, and events."""
    graph = generate(config.topology_family, config.topology_parameters, config.seed)
    decomposition = BalancedConnectedDecomposition(config.leaf_size)
    tree = decomposition.decompose(graph)
    pairs, pairs_sampled = _pairs(graph, config.pair_sample_count, config.seed + 1)
    summary_configs = _summary_configs(config)
    runs = [_make_run(graph, graph, tree, summary_config) for summary_config in summary_configs]
    flat = FlatRouting(graph)
    flat_state = flat.snapshot()
    events = [*single_link_events(graph, tree), *single_node_events(graph)]
    if graph.edges and config.random_failure_link_count <= len(graph.edges):
        events.append(random_link_set_event(graph, config.random_failure_link_count, config.seed + 2))
    selected_events = sample_events(events, config.failure_sample_count, config.seed + 3)
    failures = [_run_failure(graph, event, tree, runs, flat_state) for event in selected_events]
    return {
        "schema": {"name": "netsynth.phase2", "version": METRIC_SCHEMA_VERSION},
        "topology": _topology_metadata(config, graph),
        "decomposition_control": {"parameters": decomposition.parameters, **tree.describe(graph)},
        "sampling": {
            "pairs_sampled": pairs_sampled,
            "pair_count": len(pairs),
            "failures_sampled": len(selected_events) < len(events),
            "failure_count": len(selected_events),
            "available_failure_count": len(events),
        },
        "strategies": {
            "flat": {
                "parameters": {"name": flat.name, "knowledge": "full_physical_topology"},
                "routing_state": routing_state(flat_state, graph.nodes),
                "path_quality": path_quality(graph, flat, flat, pairs, tree, sampled=pairs_sampled),
            },
            **{
                run.config.name: {
                    "parameters": run.config.to_dict(),
                    "routing_state": routing_state(run.state, graph.nodes),
                    "path_quality": path_quality(graph, flat, run.routing, pairs, tree, sampled=pairs_sampled),
                }
                for run in runs
            },
        },
        "failure_experiments": failures,
        "failure_distributions": _failure_distributions(failures, [run.config.name for run in runs]),
        "state_accounting": {
            "normalized_scalar_sizes": {
                "forwarding_entry": 3,
                "topology_node": 1,
                "topology_link": 4,
                "quotient_adjacency": 3,
                "crossing_link": 4,
                "portal_record": 1,
                "distance_or_attachment": 3,
                "boundary_bundle": "4 + 4 per representative crossing",
            },
            "ownership": "one logical copy at every physical node consuming its ancestor-scope summaries",
            "excluded": "Python overhead, caches, transient shortest-path work, and availability replication",
        },
    }


def _summary_configs(config: ExperimentConfig) -> list[SummaryConfig]:
    counts = tuple(dict.fromkeys(config.s2_landmark_counts))
    if not counts or any(count < 1 for count in counts):
        raise ValueError("s2_landmark_counts must contain positive values")
    return [
        SummaryConfig("s0"),
        SummaryConfig("s1", bundle_representatives=config.s1_bundle_representatives),
        *(SummaryConfig("s2", landmark_count=count) for count in counts),
        SummaryConfig("s3"),
    ]


def _make_run(graph: Graph, reference: Graph, tree: ScopeTree, config: SummaryConfig) -> _StrategyRun:
    build = SummaryBuilder(tree, reference, config).build(graph)
    routing = CompressedRouting(build)
    return _StrategyRun(config, build, routing, routing.snapshot())


def _run_failure(
    graph: Graph,
    event: FailureEvent,
    tree: ScopeTree,
    before_runs: list[_StrategyRun],
    flat_before: RoutingSnapshot,
) -> dict[str, Any]:
    failed = event.apply(graph)
    flat_after = FlatRouting(failed, graph).snapshot()
    strategies: dict[str, Any] = {}
    for before in before_runs:
        after = _make_run(failed, graph, tree, before.config)
        strategy_churn = churn(before.state, after.state, graph.nodes)
        strategies[before.config.name] = {
            "churn": strategy_churn,
            "recovery_churn": churn(after.state, before.state, graph.nodes),
            "failure_locality": failure_locality(before.build, after.build),
        }
    flat_churn = churn(flat_before, flat_after, graph.nodes)
    return {
        "event": event.to_dict(),
        "remaining_node_count": len(failed.nodes),
        "remaining_link_count": len(failed.edges),
        "flat": {"churn": flat_churn, "recovery_churn": churn(flat_after, flat_before, graph.nodes)},
        "strategies": strategies,
    }


def _failure_distributions(results: list[dict[str, Any]], strategy_names: list[str]) -> dict[str, Any]:
    return {
        "flat": _churn_distribution(results, "flat"),
        **{
            name: {
                **_churn_distribution(results, name),
                "recomputed_scopes": distribution(
                    (
                        float(result["strategies"][name]["failure_locality"]["recomputed_scope_count"])
                        for result in results
                    ),
                    (50, 95, 99),
                ),
                "reached_root_fraction": (
                    sum(result["strategies"][name]["failure_locality"]["reached_root"] for result in results)
                    / len(results)
                    if results
                    else None
                ),
            }
            for name in strategy_names
        },
    }


def _churn_distribution(results: list[dict[str, Any]], name: str) -> dict[str, Any]:
    def value(result: dict[str, Any], field: str) -> float:
        section = result["flat"] if name == "flat" else result["strategies"][name]
        return float(section["churn"][field])

    return {
        "changed_objects": distribution((value(result, "changed_objects") for result in results), (50, 95, 99)),
        "changed_normalized_size": distribution(
            (value(result, "changed_normalized_size") for result in results), (50, 95, 99)
        ),
        "changed_forwarding_objects": distribution(
            (value(result, "changed_forwarding_objects") for result in results), (50, 95, 99)
        ),
        "changed_local_detail_objects": distribution(
            (value(result, "changed_local_detail_objects") for result in results), (50, 95, 99)
        ),
        "changed_global_detail_objects": distribution(
            (value(result, "changed_global_detail_objects") for result in results), (50, 95, 99)
        ),
        "changed_remote_summary_objects": distribution(
            (value(result, "changed_remote_summary_objects") for result in results), (50, 95, 99)
        ),
        "changed_recipient_fraction": distribution(
            (value(result, "changed_recipient_fraction") for result in results), (50, 95, 99)
        ),
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
