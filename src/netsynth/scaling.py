"""Small, reproducible R0 and scoped-potential scaling experiments."""

from __future__ import annotations

import random
from typing import Any

from netsynth.attachments import AttachmentCompilation, Lookahead, compile_attachment_forwarding
from netsynth.decomposition import BalancedConnectedDecomposition
from netsynth.forwarding import LocatorCatalog, compile_forwarding, compile_scoped_potentials, execute_forwarding
from netsynth.graph import Graph
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
            potential = compile_scoped_potentials(graph, tree, catalog)
            attachment_compilations: dict[Lookahead, AttachmentCompilation] = {
                lookahead: compile_attachment_forwarding(graph, graph, tree, catalog, lookahead)
                for lookahead in (1, 2, 3, "full")
            }
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
            potential_outcomes = [
                execute_forwarding(potential.network, graph, source, catalog.by_node[target], 4 * size)
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
            after_potential = compile_scoped_potentials(failed, tree, catalog)
            after_attachments: dict[Lookahead, AttachmentCompilation] = {
                lookahead: compile_attachment_forwarding(failed, graph, tree, catalog, lookahead)
                for lookahead in (1, 2, 3, "full")
            }
            state = routing_state(network.state, graph.nodes)
            potential_state = routing_state(potential.network.state, graph.nodes)
            eligible_sizes = [
                float(len(hops))
                for knowledge in potential.network.knowledge.values()
                for hops in (() if knowledge.eligible is None else knowledge.eligible.values())
            ]
            attachment_results = _attachment_scaling_results(
                graph,
                flat,
                pairs,
                catalog,
                attachment_compilations,
                after_attachments,
            )
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
                    "scoped_potential": {
                        "delivered": sum(result.status == "delivered" for result in potential_outcomes),
                        "no_route": sum(result.status == "no_route" for result in potential_outcomes),
                        "loop": sum(result.status == "loop" for result in potential_outcomes),
                        "hop_budget_exhausted": sum(
                            result.status == "hop_budget_exhausted" for result in potential_outcomes
                        ),
                        "weighted_stretch": distribution(
                            (
                                result.cost / shortest.cost
                                for (source, target), result in zip(pairs, potential_outcomes, strict=True)
                                if result.status == "delivered" and (shortest := flat.route(source, target)) is not None
                            ),
                            (50, 95, 99),
                        ),
                        "state": potential_state,
                        "eligible_next_hop_count": distribution(eligible_sizes, (50, 95, 99)),
                        "nonempty_eligible_next_hop_count": distribution(
                            (size for size in eligible_sizes if size > 0), (50, 95, 99)
                        ),
                        "fixed_point_rounds": distribution(
                            (float(value) for value in potential.rounds.values()), (50, 95, 99)
                        ),
                        "failure_churn": churn(potential.network.state, after_potential.network.state, graph.nodes),
                    },
                    "attachment_lookahead": attachment_results,
                }
            )
    return {
        "schema": {"name": "netsynth.phase4.scaling", "version": "4.0"},
        "seed": seed,
        "controls": ["flat", "r0"],
        "candidate": {
            "name": "hierarchical_attachment_lookahead",
            "levels": [1, 2, 3, "full"],
            "r0_consumed": False,
        },
        "requested_pair_sample_count": pair_sample_count,
        "rows": rows,
        "interpretation": "modest empirical sizes only; no asymptotic claim",
    }


def _attachment_scaling_results(
    graph: Graph,
    flat: FlatRouting,
    pairs: list[tuple[int, int]],
    catalog: LocatorCatalog,
    before: dict[Lookahead, AttachmentCompilation],
    after: dict[Lookahead, AttachmentCompilation],
) -> dict[str, Any]:
    costs: dict[Lookahead, list[float]] = {}
    result: dict[str, Any] = {}
    for lookahead, compilation in before.items():
        outcomes = [
            execute_forwarding(compilation.network, graph, source, catalog.by_node[target], 4 * len(graph.nodes))
            for source, target in pairs
        ]
        costs[lookahead] = [outcome.cost for outcome in outcomes]
        state = routing_state(compilation.network.state, graph.nodes)
        result[f"h{lookahead}"] = {
            "delivered": sum(outcome.status == "delivered" for outcome in outcomes),
            "loop": sum(outcome.status == "loop" for outcome in outcomes),
            "no_route": sum(outcome.status == "no_route" for outcome in outcomes),
            "state": state,
            "attachment_state": state["by_category"].get(
                "attachment_advertisement", {"object_total": 0, "normalized_size_total": 0}
            ),
            "total_stretch": distribution(
                (
                    outcome.cost / shortest.cost
                    for (source, target), outcome in zip(pairs, outcomes, strict=True)
                    if (shortest := flat.route(source, target)) is not None
                ),
                (50, 95, 99),
            ),
            "failure_churn": churn(compilation.network.state, after[lookahead].network.state, graph.nodes),
        }
    full = costs["full"]
    result["hierarchy_stretch"] = distribution(
        (
            cost / shortest.cost
            for (source, target), cost in zip(pairs, full, strict=True)
            if (shortest := flat.route(source, target)) is not None
        ),
        (50, 95, 99),
    )
    result["information_stretch"] = {
        f"h{lookahead}": distribution(
            (cost / reference for cost, reference in zip(costs[lookahead], full, strict=True)), (50, 95, 99)
        )
        for lookahead in (1, 2, 3)
    }
    return result


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
