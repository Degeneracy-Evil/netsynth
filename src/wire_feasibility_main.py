"""Emit the tiny actual-wire/node-local feasibility experiment."""

import json

from netsynth.wire_probe import run_probe


def main() -> None:
    print(json.dumps(run_probe(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
