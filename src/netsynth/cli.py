"""Command-line interface for reproducible Phase-5 decomposition experiments."""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import replace
from pathlib import Path
from typing import Any

from netsynth.phase3 import Phase3Config, run_phase3


def default_suite(seed: int) -> list[Phase3Config]:
    """Use exhaustive small instances, two seeds, and weighted/relabel controls."""
    families: list[tuple[str, dict[str, int | float | str]]] = [
        ("tree", {"node_count": 16, "branching": 2}),
        ("mesh2d", {"rows": 4, "columns": 4}),
        ("torus2d", {"rows": 4, "columns": 4}),
        ("erdos_renyi", {"node_count": 16, "probability": 0.2}),
        ("expander_like", {"node_count": 16, "chords_per_node": 3}),
    ]
    suite = [
        Phase3Config(family, parameters, seed=seed + instance, leaf_size=4, failure_sample_count=2)
        for family, parameters in families
        for instance in range(2)
    ]
    suite.extend(
        Phase3Config(
            family,
            parameters,
            seed=seed,
            leaf_size=4,
            failure_sample_count=2,
            label_permutation_seed=seed + 99,
        )
        for family, parameters in families
    )
    suite.extend(
        Phase3Config(
            family,
            parameters,
            seed=seed,
            leaf_size=4,
            failure_sample_count=2,
            fixed_structure_label_seed=seed + 199,
        )
        for family, parameters in families
    )
    suite.extend(
        Phase3Config(
            family,
            parameters,
            seed=seed,
            leaf_size=4,
            failure_sample_count=2,
            cost_profile="skewed",
        )
        for family, parameters in families
    )
    return [replace(config, decomposition=decomposition) for config in suite for decomposition in ("d0", "d1", "dbad")]


def parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    result = argparse.ArgumentParser(description="NetSynth Phase-5 metric-decomposition simulator")
    result.add_argument("--config", type=Path, help="JSON file containing one config object or a list")
    result.add_argument("--output", type=Path, help="write JSON to this file instead of stdout")
    result.add_argument("--seed", type=int, default=20260916, help="seed for the built-in suite")
    return result


def run(argv: list[str] | None = None) -> dict[str, Any]:
    """Run configured experiments and return the serializable document."""
    arguments = parser().parse_args(argv)
    configs = _load_configs(arguments.config) if arguments.config else default_suite(arguments.seed)
    experiments = [run_phase3(config) for config in configs]
    document = {
        "suite": "netsynth.phase5",
        "experiments": experiments,
        "decomposition_comparison": _decomposition_comparison(experiments),
    }
    rendered = json.dumps(document, indent=2, sort_keys=True) + "\n"
    if arguments.output is None:
        print(rendered, end="")
    else:
        arguments.output.write_text(rendered, encoding="utf-8")
    return document


def _load_configs(path: Path) -> list[Phase3Config]:
    raw: Any = json.loads(path.read_text(encoding="utf-8"))
    items = raw if isinstance(raw, list) else [raw]
    if not all(isinstance(item, dict) for item in items):
        raise ValueError("config must be an object or list of objects")
    return [Phase3Config(**item) for item in items]


def _decomposition_comparison(experiments: list[dict[str, Any]]) -> dict[str, Any]:
    points = [
        {
            "decomposition": result["decomposition_control"]["strategy_id"],
            "distortion": result["decomposition_control"]["quality"]["aggregate_distortion"]["mean"],
            "boundary": result["decomposition_control"]["quality"]["boundary_interfaces"]["mean"],
            "hierarchy_stretch": result["strategies"]["attachment_comparison"]["hierarchy_stretch_full_over_flat"][
                "mean"
            ],
            "full_state": result["strategies"]["attachment_hfull"]["distributed_state"]["normalized_size_total"],
            "scope_break_fraction": (
                sum(not row["prefix_monotone_scope_connectivity"] for row in result["failure_experiments"])
                / len(result["failure_experiments"])
                if result["failure_experiments"]
                else None
            ),
        }
        for result in experiments
    ]
    usable = [point for point in points if isinstance(point["distortion"], (int, float))]
    candidate_points = [point for point in usable if point["decomposition"] in {"d0", "d1"}]
    return {
        "points": points,
        "distortion_hierarchy_pearson": _pearson(
            [float(point["distortion"]) for point in usable],
            [float(point["hierarchy_stretch"]) for point in usable],
        ),
        "d0_d1_distortion_hierarchy_pearson": _pearson(
            [float(point["distortion"]) for point in candidate_points],
            [float(point["hierarchy_stretch"]) for point in candidate_points],
        ),
        "interpretation": "paired empirical decomposition points; correlation is not a causal claim",
    }


def _pearson(left: list[float], right: list[float]) -> float | None:
    if len(left) < 2 or len(left) != len(right):
        return None
    left_mean, right_mean = sum(left) / len(left), sum(right) / len(right)
    numerator = sum((x - left_mean) * (y - right_mean) for x, y in zip(left, right, strict=True))
    left_scale = math.sqrt(sum((x - left_mean) ** 2 for x in left))
    right_scale = math.sqrt(sum((y - right_mean) ** 2 for y in right))
    return numerator / (left_scale * right_scale) if left_scale and right_scale else None
