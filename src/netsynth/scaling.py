"""Small, reproducible R0-only state/reachability scaling experiments."""

from __future__ import annotations

import random
from typing import Any

from netsynth.decomposition import BalancedConnectedDecomposition
from netsynth.forwarding import LocatorCatalog, compile_forwarding, execute_forwarding
from netsynth.metrics import churn, distribution, failure_locality, routing_state
from netsynth.routing import FlatRouting
from netsynth.summaries import SummaryBuilder, SummaryConfig
from netsynth.topology import generate


def run_scaling(
    sizes: tuple[int, ...] = (16, 32, 64, 128),
    families: tuple[str, ...] = ("tree", "mesh2d", "expander_like"),
    seed: int = 20260916,
    pair_sample_count: int = 128,
) -> dict[str, Any]:
    """Measure several modest sizes without implying asymptotic complexity."""
    rows: list[dict[str, Any]] = []
    for family in families:
        for size in sizes:
            parameters = _parameters(family, size)
            graph = generate(family, parameters, seed)
            tree = BalancedConnectedDecomposition(max(2, min(8, size // 8))).decompose(graph)
            catalog = LocatorCatalog.from_tree(tree)
            builder = SummaryBuilder(tree, graph, SummaryConfig("r0"))
            before = builder.build(graph)
            network = compile_forwarding(before, catalog)
            flat = FlatRouting(graph)
            all_pairs = [
                (source, target) for source in sorted(graph.nodes) for target in sorted(graph.nodes) if source != target
            ]
            sampled = pair_sample_count < len(all_pairs)
            pairs = random.Random(seed + size).sample(all_pairs, min(pair_sample_count, len(all_pairs)))
            outcomes = [
                execute_forwarding(network, graph, source, catalog.by_node[target], 4 * size)
                for source, target in pairs
            ]
            stretches = [
                result.cost / shortest.cost
                for (source, target), result in zip(pairs, outcomes, strict=True)
                if result.status == "delivered" and (shortest := flat.route(source, target)) is not None
            ]
            boundary_counts = [len(view.summary.boundary_nodes) for view in before.views.values()]
            candidate = next(
                (
                    edge
                    for edge in graph.edges
                    if (failed := graph.without(edges=frozenset((edge.key,)))).is_connected()
                    and all(failed.induced(scope.members).is_connected() for scope in tree.scopes())
                ),
                graph.edges[0],
            )
            failed = graph.without(edges=frozenset((candidate.key,)))
            after = builder.build(failed)
            after_network = compile_forwarding(after, catalog)
            state = routing_state(network.state, graph.nodes)
            rows.append(
                {
                    "family": family,
                    "requested_node_count": size,
                    "topology_parameters": parameters,
                    "node_count": len(graph.nodes),
                    "link_count": len(graph.edges),
                    "decomposition": {"strategy": "balanced_connected", "leaf_size": max(2, min(8, size // 8))},
                    "pairs": {"count": len(pairs), "sampled": sampled},
                    "delivered": sum(result.status == "delivered" for result in outcomes),
                    "no_route": sum(result.status == "no_route" for result in outcomes),
                    "loop": sum(result.status == "loop" for result in outcomes),
                    "hop_budget_exhausted": sum(result.status == "hop_budget_exhausted" for result in outcomes),
                    "invalid_next_hop": sum(result.status == "invalid_next_hop" for result in outcomes),
                    "weighted_stretch": distribution(stretches, (50, 95, 99)),
                    "state_total": state["normalized_size_total"],
                    "flat_normalized_size_reference": len(graph.nodes)
                    * (3 * (len(graph.nodes) - 1) + len(graph.nodes) + 4 * len(graph.edges)),
                    "state_per_node": state["per_node_normalized_size"],
                    "reachability_summary_state": {
                        category: state["by_category"].get(category, {"object_total": 0, "normalized_size_total": 0})
                        for category in ("reachability_boundary", "reachability_component", "reachability_interface")
                    },
                    "boundary_count": distribution((float(count) for count in boundary_counts), (50, 95, 99)),
                    "failure": {
                        "link": list(candidate.key),
                        "physical_graph_connected": failed.is_connected(),
                        "prefix_monotone_scope_connectivity": all(
                            failed.induced(scope.members).is_connected() for scope in tree.scopes()
                        ),
                        "churn": churn(network.state, after_network.state, graph.nodes),
                        "locality": failure_locality(before, after),
                    },
                }
            )
    return {
        "schema": {"name": "netsynth.phase3_1.scaling", "version": "3.1"},
        "seed": seed,
        "summary": {"name": "r0", "abstract_component_edge_cost": 2.0},
        "requested_pair_sample_count": pair_sample_count,
        "rows": rows,
        "interpretation": "modest empirical sizes only; no asymptotic claim",
    }


def _parameters(family: str, size: int) -> dict[str, int | float | str]:
    if size < 2:
        raise ValueError("size must be at least two")
    if family == "tree":
        return {"node_count": size, "branching": 2}
    if family == "mesh2d":
        rows = 2 ** ((size.bit_length() - 1) // 2)
        if size % rows:
            raise ValueError("mesh size must be divisible by its chosen row count")
        return {"rows": rows, "columns": size // rows}
    if family == "expander_like":
        return {"node_count": size, "chords_per_node": 3}
    raise ValueError(f"unsupported scaling family: {family}")
