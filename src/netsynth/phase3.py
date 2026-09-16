"""Phase-3 oracle versus knowledge-disciplined distributed experiments."""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from netsynth.decomposition import BalancedConnectedDecomposition, ScopeTree
from netsynth.failures import random_link_set_event, sample_events, single_link_events, single_node_events
from netsynth.forwarding import ForwardingNetwork, Locator, LocatorCatalog, compile_forwarding, execute_forwarding
from netsynth.graph import Edge, Graph, Node
from netsynth.metrics import churn, distribution, failure_locality, path_quality, routing_state
from netsynth.routing import CompressedRouting, FlatRouting
from netsynth.summaries import SummaryBuilder, SummaryConfig
from netsynth.topology import generate

SCHEMA_VERSION = "3.0"


@dataclass(frozen=True)
class Phase3Config:
    """One reproducible physical instance and one fixed-decomposition strategy matrix."""

    topology_family: str
    topology_parameters: dict[str, int | float | str]
    seed: int = 0
    leaf_size: int = 8
    pair_sample_count: int | None = None
    failure_sample_count: int | None = 8
    random_failure_link_count: int = 2
    s1_bundle_representatives: int = 2
    s2_landmark_counts: tuple[int, ...] = (1, 2, 4)
    cost_profile: str = "unit"
    label_permutation_seed: int | None = None
    hop_budget: int | None = None


def run_phase3(config: Phase3Config) -> dict[str, Any]:
    """Compare flat, recursive oracle, and distributed routes on the same instance."""
    graph = _transform(generate(config.topology_family, config.topology_parameters, config.seed), config)
    tree = BalancedConnectedDecomposition(config.leaf_size).decompose(graph)
    catalog = LocatorCatalog.from_tree(tree)
    flat = FlatRouting(graph)
    pairs, sampled = _pairs(graph, config.pair_sample_count, config.seed + 1)
    budget = config.hop_budget if config.hop_budget is not None else 4 * len(graph.nodes)
    if budget < 0:
        raise ValueError("hop_budget cannot be negative")
    configs = [
        SummaryConfig("s0"),
        SummaryConfig("s1", bundle_representatives=config.s1_bundle_representatives),
        *(SummaryConfig("s2", landmark_count=k) for k in dict.fromkeys(config.s2_landmark_counts)),
        SummaryConfig("s3"),
    ]
    if not config.s2_landmark_counts or any(k < 1 for k in config.s2_landmark_counts):
        raise ValueError("S2 landmark counts must be positive")
    prepared = []
    strategies: dict[str, Any] = {
        "flat": {
            "state": routing_state(flat.snapshot(), graph.nodes),
            "path": path_quality(graph, flat, flat, pairs, tree, sampled=sampled),
        }
    }
    for summary_config in configs:
        builder = SummaryBuilder(tree, graph, summary_config)
        build = builder.build(graph)
        oracle = CompressedRouting(build)
        network = compile_forwarding(build, catalog)
        prepared.append((summary_config, builder, build, network))
        strategies[summary_config.name] = {
            "parameters": summary_config.to_dict(),
            "distributed_state": routing_state(network.state, graph.nodes),
            "locator_reference_components": _reference_components(network),
            "oracle_phase2_state_reference": routing_state(oracle.snapshot(), graph.nodes),
            "recursive_oracle": path_quality(graph, flat, oracle, pairs, tree, sampled=sampled),
            "distributed": _distributed_quality(graph, flat, oracle, network, pairs, tree, budget, sampled),
        }
    events = [*single_link_events(graph, tree), *single_node_events(graph)]
    if 0 < config.random_failure_link_count <= len(graph.edges):
        events.append(random_link_set_event(graph, config.random_failure_link_count, config.seed + 2))
    selected = sample_events(events, config.failure_sample_count, config.seed + 3)
    failures = []
    for event in selected:
        failed = event.apply(graph)
        row: dict[str, Any] = {"event": event.to_dict(), "strategies": {}}
        for summary_config, builder, build, network in prepared:
            after = builder.build(failed)
            after_network = compile_forwarding(after, catalog)
            row["strategies"][summary_config.name] = {
                "distributed_churn": churn(network.state, after_network.state, graph.nodes),
                "failure_locality": failure_locality(build, after),
            }
        failures.append(row)
    return {
        "schema": {"name": "netsynth.phase3", "version": SCHEMA_VERSION},
        "topology": _topology_metadata(config, graph),
        "decomposition_control": {
            "parameters": {"name": "balanced_connected", "leaf_size": config.leaf_size},
            **tree.describe(graph),
        },
        "sampling": {
            "pairs_sampled": sampled,
            "pair_count": len(pairs),
            "requested_pair_sample_count": config.pair_sample_count,
            "failures_sampled": len(selected) < len(events),
            "failure_count": len(selected),
            "requested_failure_sample_count": config.failure_sample_count,
            "available_failure_count": len(events),
        },
        "failure_parameters": {"random_failure_link_count": config.random_failure_link_count},
        "forwarding": {
            "hop_budget": budget,
            "rule": "progressive_locator_prefix",
            "fib": "deterministic_single_next_hop",
        },
        "locator": {
            "per_node_components": distribution(
                (float(locator.component_count) for locator in catalog.by_node.values()), (50, 95, 99)
            ),
            "packet_destination_components": distribution(
                (float(catalog.by_node[target].component_count) for _source, target in pairs), (50, 95, 99)
            ),
        },
        "strategies": strategies,
        "failure_experiments": failures,
        "failure_distributions": {
            summary_config.name: {
                "changed_distributed_objects": distribution(
                    (
                        float(row["strategies"][summary_config.name]["distributed_churn"]["changed_objects"])
                        for row in failures
                    ),
                    (50, 95, 99),
                ),
                "changed_recipient_fraction": distribution(
                    (
                        float(row["strategies"][summary_config.name]["distributed_churn"]["changed_recipient_fraction"])
                        for row in failures
                    ),
                    (50, 95, 99),
                ),
                "reached_root_fraction": (
                    sum(row["strategies"][summary_config.name]["failure_locality"]["reached_root"] for row in failures)
                    / len(failures)
                    if failures
                    else None
                ),
            }
            for summary_config in configs
        },
        "definitions": {
            "oracle": "Phase-2 recursive path oracle; may query hidden remote target interior",
            "distributed": "compiled per-node FIB lookup; physical graph used only by executor",
            "state": "persistent owner-local and remote summary/FIB objects; locator reference components charged",
            "excluded": "simulator route cache, transient Dijkstra work, availability replication",
        },
    }


def _distributed_quality(
    graph: Graph,
    flat: FlatRouting,
    oracle: CompressedRouting,
    network: ForwardingNetwork,
    pairs: list[tuple[Node, Node]],
    tree: ScopeTree,
    budget: int,
    sampled: bool,
) -> dict[str, Any]:
    statuses = dict.fromkeys(("delivered", "no_route", "invalid_next_hop", "loop", "hop_budget_exhausted"), 0)
    stretches: list[float] = []
    hop_stretches: list[float] = []
    overhead: list[float] = []
    oracle_gaps: list[float] = []
    exact = 0
    grouped: dict[str, list[float]] = {"same_leaf": [], "sibling_scopes": [], "distant_scopes": []}
    grouped_statuses: dict[str, dict[str, int]] = {name: dict.fromkeys(statuses, 0) for name in grouped}
    for source, target in pairs:
        result = execute_forwarding(network, graph, source, network.catalog.by_node[target], budget)
        statuses[result.status] += 1
        relation = _relationship(tree, source, target)
        grouped_statuses[relation][result.status] += 1
        shortest = flat.route(source, target)
        if result.status != "delivered" or shortest is None:
            continue
        stretch = result.cost / shortest.cost
        stretches.append(stretch)
        hop_stretches.append(result.hops / (len(shortest.nodes) - 1))
        overhead.append(result.cost - shortest.cost)
        exact += abs(stretch - 1.0) < 1e-12
        oracle_path = oracle.route(source, target)
        if oracle_path is not None:
            oracle_gaps.append(result.cost / oracle_path.cost)
        grouped[relation].append(stretch)
    return {
        "sampled": sampled,
        "requested_pair_count": len(pairs),
        "statuses": statuses,
        "weighted_cost_stretch": distribution(stretches, (50, 95, 99)),
        "hop_count_stretch": distribution(hop_stretches, (50, 95, 99)),
        "additive_cost_overhead": distribution(overhead, (50, 95, 99)),
        "oracle_gap": distribution(oracle_gaps, (50, 95, 99)),
        "exactly_shortest_fraction": exact / len(stretches) if stretches else None,
        "by_relationship": {
            name: {"statuses": grouped_statuses[name], "weighted_cost_stretch": distribution(values, (50, 95, 99))}
            for name, values in grouped.items()
        },
    }


def _relationship(tree: ScopeTree, source: Node, target: Node) -> str:
    left, right = tree.lineage(source), tree.lineage(target)
    if left[-1] == right[-1]:
        return "same_leaf"
    common = 0
    while common < min(len(left), len(right)) and left[common] == right[common]:
        common += 1
    return "sibling_scopes" if common == len(left) - 1 == len(right) - 1 else "distant_scopes"


def _reference_components(network: ForwardingNetwork) -> dict[str, Any]:
    prefix_counts: list[float] = []
    portal_counts: list[float] = []
    crossing_counts: list[float] = []
    for (_owner, category, _scope, _identifier), record in network.state.objects.items():
        if category == "forwarding_entry":
            key = record.value[0]
            if isinstance(key, Locator):
                prefix_counts.append(float(key.component_count))
            elif isinstance(key, tuple):
                prefix_counts.append(float(len(key)))
        elif category == "portal_record":
            portal_counts.append(float(record.normalized_size))
        elif category == "crossing_locator_reference":
            crossing_counts.append(float(record.normalized_size))
    return {
        "forwarding_prefix_key_components": distribution(prefix_counts, (50, 95, 99)),
        "portal_summary_reference_normalized_components": distribution(portal_counts, (50, 95, 99)),
        "crossing_reference_normalized_components": distribution(crossing_counts, (50, 95, 99)),
    }


def _pairs(graph: Graph, count: int | None, seed: int) -> tuple[list[tuple[Node, Node]], bool]:
    pairs = [(source, target) for source in sorted(graph.nodes) for target in sorted(graph.nodes) if source != target]
    if count is None or count >= len(pairs):
        return pairs, False
    return random.Random(seed).sample(pairs, count), True


def _transform(graph: Graph, config: Phase3Config) -> Graph:
    if config.cost_profile not in {"unit", "moderate", "skewed"}:
        raise ValueError("cost_profile must be unit, moderate, or skewed")
    if config.cost_profile != "unit":
        rng = random.Random(config.seed + 101)
        costs = (1, 2, 3, 5) if config.cost_profile == "moderate" else (1, 1, 1, 12, 25)
        graph = Graph(
            set(graph.nodes),
            [Edge(edge.left, edge.right, float(rng.choice(costs)), edge.capacity) for edge in graph.edges],
        )
    if config.label_permutation_seed is not None:
        rng = random.Random(config.label_permutation_seed)
        old = sorted(graph.nodes)
        new = old.copy()
        rng.shuffle(new)
        mapping = dict(zip(old, new, strict=True))
        graph = Graph(
            set(new), [Edge(mapping[edge.left], mapping[edge.right], edge.cost, edge.capacity) for edge in graph.edges]
        )
    return graph


def _topology_metadata(config: Phase3Config, graph: Graph) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "family": config.topology_family,
        "parameters": config.topology_parameters,
        "seed": config.seed,
        "node_count": len(graph.nodes),
        "link_count": len(graph.edges),
        "cost_profile": config.cost_profile,
        "label_permutation_seed": config.label_permutation_seed,
    }
    if config.topology_family == "json":
        metadata["input_sha256"] = hashlib.sha256(
            Path(str(config.topology_parameters["path"])).read_bytes()
        ).hexdigest()
    return metadata
