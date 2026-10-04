"""Run only the tiny deterministic Scale-6 semantic probe."""

import json

from netsynth.scale6_probe import run_probe


def main() -> None:
    """Emit reproducible semantic evidence, not a performance benchmark."""
    print(json.dumps(run_probe(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
