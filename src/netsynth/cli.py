"""Command-line interface for reproducible Phase-2 experiments."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from netsynth.experiment import ExperimentConfig, run_experiment


def default_suite(seed: int) -> list[ExperimentConfig]:
    """Return small favorable, geometric, irregular, and hostile experiments."""
    common: dict[str, Any] = {"seed": seed, "leaf_size": 5, "pair_sample_count": 128, "failure_sample_count": 4}
    return [
        ExperimentConfig("tree", {"node_count": 25, "branching": 2}, **common),
        ExperimentConfig("mesh2d", {"rows": 5, "columns": 5}, **common),
        ExperimentConfig("erdos_renyi", {"node_count": 25, "probability": 0.16}, **common),
        ExperimentConfig("expander_like", {"node_count": 25, "chords_per_node": 3}, **common),
    ]


def parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    result = argparse.ArgumentParser(description="NetSynth Phase-2 routing-summary simulator")
    result.add_argument("--config", type=Path, help="JSON file containing one config object or a list")
    result.add_argument("--output", type=Path, help="write JSON to this file instead of stdout")
    result.add_argument("--seed", type=int, default=20260916, help="seed for the built-in suite")
    return result


def run(argv: list[str] | None = None) -> dict[str, Any]:
    """Run configured experiments and return the serializable document."""
    arguments = parser().parse_args(argv)
    configs = _load_configs(arguments.config) if arguments.config else default_suite(arguments.seed)
    document = {"suite": "netsynth.phase2", "experiments": [run_experiment(config) for config in configs]}
    rendered = json.dumps(document, indent=2, sort_keys=True) + "\n"
    if arguments.output is None:
        print(rendered, end="")
    else:
        arguments.output.write_text(rendered, encoding="utf-8")
    return document


def _load_configs(path: Path) -> list[ExperimentConfig]:
    raw: Any = json.loads(path.read_text(encoding="utf-8"))
    items = raw if isinstance(raw, list) else [raw]
    if not all(isinstance(item, dict) for item in items):
        raise ValueError("config must be an object or list of objects")
    return [ExperimentConfig(**item) for item in items]
