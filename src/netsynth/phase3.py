"""Phase-3 oracle versus knowledge-disciplined distributed experiments."""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from netsynth.decomposition import BalancedConnectedDecomposition, Scope, ScopeTree
from netsynth.failures import random_link_set_event, sample_events, single_link_events, single_node_events
from netsynth.forwarding import (
    ForwardingNetwork,
    Locator,
    LocatorCatalog,
    compile_forwarding,
    compile_scoped_potentials,
    execute_forwarding,
)
from netsynth.graph import Edge, Graph, Node
from netsynth.metrics import churn, distribution, failure_locality, path_quality, routing_state
from netsynth.routing import CompressedRouting, FlatRouting
from netsynth.summaries import SummaryBuilder, SummaryConfig
from netsynth.topology import generate

SCHEMA_VERSION = "3.2"


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
    fixed_structure_label_seed: int | None = None
    hop_budget: int | None = None


def run_phase3(config: Phase3Config) -> dict[str, Any]:
    """Compare flat, recursive oracle, and distributed routes on the same instance."""
    graph = _transform(generate(config.topology_family, config.topology_parameters, config.seed), config)
    tree = BalancedConnectedDecomposition(config.leaf_size).decompose(graph)
    if config.fixed_structure_label_seed is not None:
        graph, tree = _relabel_structure(graph, tree, config.fixed_structure_label_seed)
    catalog = LocatorCatalog.from_tree(tree)
    flat = FlatRouting(graph)
    pairs, sampled = _pairs(graph, config.pair_sample_count, config.seed + 1)
    budget = config.hop_budget if config.hop_budget is not None else 4 * len(graph.nodes)
    if budget < 0:
        raise ValueError("hop_budget cannot be negative")
    configs = [
        SummaryConfig("r0"),
        SummaryConfig("s0"),
        SummaryConfig("s1", bundle_representatives=config.s1_bundle_representatives),
        *(SummaryConfig("s2", landmark_count=k) for k in dict.fromkeys(config.s2_landmark_counts)),
        SummaryConfig("s3"),
    ]
    if not config.s2_landmark_counts or any(k < 1 for k in config.s2_landmark_counts):
        raise ValueError("S2 landmark counts must be positive")
    prepared = []
    r0_oracle: CompressedRouting | None = None
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
        if summary_config.level == "r0":
            r0_oracle = oracle
        strategies[summary_config.name] = {
            "parameters": summary_config.to_dict(),
            "distributed_state": routing_state(network.state, graph.nodes),
            "locator_reference_components": _reference_components(network),
            "oracle_phase2_state_reference": routing_state(oracle.snapshot(), graph.nodes),
            "recursive_oracle": path_quality(graph, flat, oracle, pairs, tree, sampled=sampled),
            "distributed": _distributed_quality(graph, flat, oracle, network, pairs, tree, budget, sampled),
        }
    if r0_oracle is None:
        raise AssertionError("R0 control must be present")
    potential = compile_scoped_potentials(graph, tree, catalog)
    strategies["scoped_potential"] = {
        "parameters": {
            "update": "scoped_neighbor_bellman_fixed_point",
            "successor_rule": "strict_potential_descent",
            "r0_consumed": False,
        },
        "distributed_state": routing_state(potential.network.state, graph.nodes),
        "eligible_next_hops": _eligible_distribution(potential.network),
        "fixed_point_rounds": distribution((float(value) for value in potential.rounds.values()), (50, 95, 99)),
        "distributed": _distributed_quality(graph, flat, r0_oracle, potential.network, pairs, tree, budget, sampled),
    }
    events = [*single_link_events(graph, tree), *single_node_events(graph)]
    if 0 < config.random_failure_link_count <= len(graph.edges):
        events.append(random_link_set_event(graph, config.random_failure_link_count, config.seed + 2))
    selected = sample_events(events, config.failure_sample_count, config.seed + 3)
    failures = []
    for event in selected:
        failed = event.apply(graph)
        prefix_admissible = all(failed.induced(scope.members).is_connected() for scope in tree.scopes())
        row: dict[str, Any] = {
            "event": event.to_dict(),
            "strategies": {},
            "physical_graph_connected": failed.is_connected(),
            "prefix_monotone_scope_connectivity": prefix_admissible,
        }
        for summary_config, builder, build, network in prepared:
            after = builder.build(failed)
            after_network = compile_forwarding(after, catalog)
            row["strategies"][summary_config.name] = {
                "distributed_churn": churn(network.state, after_network.state, graph.nodes),
                "failure_locality": failure_locality(build, after),
                "reachability_classification": (
                    "physical_partition"
                    if not failed.is_connected()
                    else (
                        "prefix_constraint_violation"
                        if not prefix_admissible
                        else (
                            "boundary_relation_changed"
                            if any(
                                view.summary.connectivity_components
                                != after.views[identifier].summary.connectivity_components
                                for identifier, view in build.views.items()
                            )
                            else "internal_change_no_boundary_relation_change"
                        )
                    )
                ),
            }
            if summary_config.level == "r0" and len(graph.nodes) <= 32:
                reachable_pairs = [
                    (source, target)
                    for source in sorted(failed.nodes)
                    for target in sorted(failed.nodes)
                    if source != target and failed.shortest_path(source, target) is not None
                ]
                outcomes = [
                    execute_forwarding(after_network, failed, source, catalog.by_node[target], budget).status
                    for source, target in reachable_pairs
                ]
                row["strategies"][summary_config.name]["connected_pair_audit"] = {
                    "exhaustive": True,
                    "physically_reachable_pairs": len(reachable_pairs),
                    "delivered": outcomes.count("delivered"),
                    "false_no_route": outcomes.count("no_route"),
                    "loops": outcomes.count("loop"),
                    "hop_budget_exhausted": outcomes.count("hop_budget_exhausted"),
                }
        after_potential = compile_scoped_potentials(failed, tree, catalog)
        potential_outcomes = [
            execute_forwarding(after_potential.network, failed, source, catalog.by_node[target], budget).status
            for source in sorted(failed.nodes)
            for target in sorted(failed.nodes)
            if source != target and (len(graph.nodes) <= 32 or (source, target) in pairs)
        ]
        row["strategies"]["scoped_potential"] = {
            "distributed_churn": churn(potential.network.state, after_potential.network.state, graph.nodes),
            "potential_churn": _potential_churn(potential.network, after_potential.network, graph.nodes),
            "eligible_next_hops": _eligible_distribution(after_potential.network),
            "scope_connected_correctness_required": prefix_admissible,
            "audited_statuses": {status: potential_outcomes.count(status) for status in _STATUSES},
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
            "candidate_object": "eligible physical next-hop set; deterministic member selected for experiments",
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
        "scoped_potential_failure_distribution": {
            "changed_objects": distribution(
                (
                    float(row["strategies"]["scoped_potential"]["potential_churn"]["changed_objects"])
                    for row in failures
                ),
                (50, 95, 99),
            ),
            "changed_node_fraction": distribution(
                (
                    float(row["strategies"]["scoped_potential"]["potential_churn"]["changed_node_fraction"])
                    for row in failures
                ),
                (50, 95, 99),
            ),
            "reached_root_fraction": (
                sum(row["strategies"]["scoped_potential"]["potential_churn"]["reached_root"] for row in failures)
                / len(failures)
                if failures
                else None
            ),
        },
        "definitions": {
            "oracle": "Phase-2 recursive path oracle; may query hidden remote target interior",
            "distributed": "compiled per-node FIB lookup; physical graph used only by executor",
            "scoped_potential": "R0-independent neighbor-exchange fixed point with strict descent",
            "state": "persistent owner-local and remote summary/FIB objects; locator reference components charged",
            "excluded": "simulator route cache, transient Dijkstra work, availability replication",
        },
    }


_STATUSES = ("delivered", "no_route", "invalid_next_hop", "loop", "hop_budget_exhausted")


def _eligible_distribution(network: ForwardingNetwork) -> dict[str, Any]:
    sizes = [
        float(len(hops))
        for knowledge in network.knowledge.values()
        for hops in (() if knowledge.eligible is None else knowledge.eligible.values())
    ]
    return {
        "set_size": distribution(sizes, (50, 95, 99)),
        "nonempty_set_size": distribution((size for size in sizes if size > 0), (50, 95, 99)),
        "sets": len(sizes),
        "sets_with_multiple_choices": sum(size > 1 for size in sizes),
        "sets_without_successor": sum(size == 0 for size in sizes),
    }


def _potential_churn(before: ForwardingNetwork, after: ForwardingNetwork, nodes: frozenset[Node]) -> dict[str, Any]:
    categories = {"potential_record", "eligible_next_hop"}
    keys = {
        key
        for key in before.state.objects.keys() | after.state.objects.keys()
        if key[1] in categories and before.state.objects.get(key) != after.state.objects.get(key)
    }
    changed_nodes = {key[0] for key in keys}
    levels = sorted({key[2].count(".") for key in keys if key[2] != "local"})
    return {
        "changed_objects": len(keys),
        "changed_nodes": len(changed_nodes),
        "changed_node_fraction": len(changed_nodes) / len(nodes) if nodes else 0.0,
        "scope_depths_reached": levels,
        "reached_root": 0 in levels,
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
    statuses = dict.fromkeys(_STATUSES, 0)
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
        "fixed_structure_label_seed": config.fixed_structure_label_seed,
    }
    if config.topology_family == "json":
        metadata["input_sha256"] = hashlib.sha256(
            Path(str(config.topology_parameters["path"])).read_bytes()
        ).hexdigest()
    return metadata


def _relabel_structure(graph: Graph, tree: ScopeTree, seed: int) -> tuple[Graph, ScopeTree]:
    """Relabel graph and existing hierarchy isomorphically, without repartitioning."""
    old = sorted(graph.nodes)
    new = old.copy()
    random.Random(seed).shuffle(new)
    mapping = dict(zip(old, new, strict=True))
    relabeled_graph = Graph(
        set(new),
        [Edge(mapping[edge.left], mapping[edge.right], edge.cost, edge.capacity) for edge in graph.edges],
    )

    def remap(scope: Scope) -> Scope:
        return Scope(
            scope.identifier, frozenset(mapping[node] for node in scope.members), tuple(map(remap, scope.children))
        )

    relabeled_tree = ScopeTree(remap(tree.root))
    relabeled_tree.validate(relabeled_graph)
    return relabeled_graph, relabeled_tree
