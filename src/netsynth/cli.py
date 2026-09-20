"""Command-line interface for reproducible Phase-3.2 forwarding experiments."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from netsynth.phase3 import Phase3Config, run_phase3


def default_suite(seed: int) -> list[Phase3Config]:
    """Use exhaustive small instances, two seeds, and weighted/relabel controls."""
    families: list[tuple[str, dict[str, int | float | str]]] = [
        ("tree", {"node_count": 16, "branching": 2}),
        ("mesh2d", {"rows": 4, "columns": 4}),
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
    return suite


def parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    result = argparse.ArgumentParser(description="NetSynth Phase-3.2 distributed-forwarding simulator")
    result.add_argument("--config", type=Path, help="JSON file containing one config object or a list")
    result.add_argument("--output", type=Path, help="write JSON to this file instead of stdout")
    result.add_argument("--seed", type=int, default=20260916, help="seed for the built-in suite")
    return result


def run(argv: list[str] | None = None) -> dict[str, Any]:
    """Run configured experiments and return the serializable document."""
    arguments = parser().parse_args(argv)
    configs = _load_configs(arguments.config) if arguments.config else default_suite(arguments.seed)
    document = {"suite": "netsynth.phase3", "experiments": [run_phase3(config) for config in configs]}
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
