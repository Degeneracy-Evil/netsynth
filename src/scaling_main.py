"""Run the Phase-3.2 modest-scaling comparison experiment."""

import argparse
import json
from pathlib import Path

from netsynth.scaling import run_scaling


def main() -> None:
    """Print or save a reproducible machine-readable scaling result."""
    parser = argparse.ArgumentParser(description="NetSynth Phase-3.2 scoped-potential scaling experiment")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--seed", type=int, default=20260916)
    args = parser.parse_args()
    rendered = json.dumps(run_scaling(seed=args.seed), indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(rendered, end="")
    else:
        args.output.write_text(rendered, encoding="utf-8")


if __name__ == "__main__":
    main()
