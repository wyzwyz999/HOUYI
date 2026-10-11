#!/usr/bin/env python3
"""HOUYI result audit — read-only."""

import argparse
import json
from pathlib import Path


FILES = {
    1: "ring1_targets.json",
    7: "ring7_fiber_targets.json",
    8: "ring8_fiber_binders.json",
    9: "ring9_reprogrammed_fibers.json",
    10: "nanosyringes.json",
}


def load_json(path):
    if not path.is_file():
        return None, "MISSING"
    try:
        with path.open(encoding="utf-8") as f:
            return json.load(f), "OK"
    except (OSError, ValueError) as e:
        return None, f"INVALID: {e}"


def audit(root, species):
    path = root / species
    if not path.is_dir():
        raise SystemExit(f"ERROR: result directory missing: {path}")

    state, state_status = load_json(path / "pipeline_state.json")

    print("=" * 60)
    print("HOUYI RESULT AUDIT")
    print("Species:", species)
    print("State:", state_status)

    if isinstance(state, dict):
        print("State organism:", state.get("organism"))

        if state.get("organism", "").lower().replace(" ", "_") != species:
            print("WARNING: organism mismatch")

        rings = state.get("rings", {})

        print("\nRING STATUS")
        for i in range(1, 11):
            info = rings.get(str(i), {})
            print(f"Ring{i}: {info.get('status', 'UNKNOWN')}")

    print("\nOUTPUT FILES")

    for ring, filename in FILES.items():
        data, status = load_json(path / filename)

        count = (
            len(data)
            if isinstance(data, (list, dict))
            else "N/A"
        )

        print(f"Ring{ring}: {filename} | {status} | count={count}")

        if ring == 10 and isinstance(data, list):
            complete = sum(
                item.get("complete") is True
                for item in data
                if isinstance(item, dict)
            )
            print(f"Ring10 COMPLETE: {complete}/{len(data)}")

    print("\nAUDIT_FINISHED")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--species", required=True)
    parser.add_argument(
        "--root",
        default="results/by_organism"
    )
    args = parser.parse_args()

    audit(Path(args.root), args.species)


if __name__ == "__main__":
    main()
