"""Run the tiny resource-cost validator; all assumptions travel with the JSON."""

import argparse
import json

from netsynth.resource_economics import Profile, run_study


def main() -> None:
    """Print reproducible accounting, not a performance benchmark."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--control-hops", type=int, default=2, help="assumed one-way control distance, not measured")
    parser.add_argument("--payload-bytes", type=int, default=128)
    parser.add_argument("--usable-packet-size", type=int, default=512)
    args = parser.parse_args()
    print(
        json.dumps(
            run_study(Profile(args.control_hops, args.payload_bytes, args.usable_packet_size)), indent=2, sort_keys=True
        )
    )


if __name__ == "__main__":
    main()
