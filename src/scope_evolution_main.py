"""Run the tiny hand-selected structural-control semantic probe."""

import json

from netsynth.scope_evolution_probe import run_probe


def main() -> None:
    print(json.dumps(run_probe(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
