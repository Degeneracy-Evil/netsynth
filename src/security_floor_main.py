"""Run only the tiny deterministic Security Floor semantic probe."""

import json

from netsynth.security_floor_probe import run_probe


def main() -> None:
    """Print semantic evidence, never private keys or traffic keys."""
    print(json.dumps(run_probe(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
