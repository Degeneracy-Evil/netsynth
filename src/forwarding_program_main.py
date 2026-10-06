"""Print the tiny compiled-forwarding semantic probe, without benchmarking."""

import json

from netsynth.forwarding_program_probe import run_probe


def main() -> None:
    """Emit deterministic, machine-readable resource accounting."""
    print(json.dumps(run_probe(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
