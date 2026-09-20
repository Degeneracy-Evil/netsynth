"""Run the tiny Scale-4 semantic probe and emit machine-readable JSON."""

import json

from netsynth.scale4_probe import run_probe


def main() -> None:
    """Print the single adversarial probe result."""
    print(json.dumps(run_probe(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
