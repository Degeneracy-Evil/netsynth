"""Run the tiny Scale-5 semantic probe."""

import json

from netsynth.scale5_probe import run_probe


def main() -> None:
    """Print reproducible semantic evidence as JSON."""
    print(json.dumps(run_probe(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
