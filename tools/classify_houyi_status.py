#!/usr/bin/env python3
"""HOUYI computational output status classification."""

import json
import argparse
from pathlib import Path


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def classify(path):
    state = read_json(path / "pipeline_state.json")
    nano = read_json(path / "nanosyringes.json")
    receptors = read_json(path / "ring7_fiber_targets.json")

    if not isinstance(state, dict):
        return "INVALID_STATE"

    if not isinstance(nano, list):
        return "MISSING_OUTPUT"

    complete = sum(
        isinstance(x, dict) and x.get("complete") is True
        for x in nano
    )

    if nano and complete == len(nano):
        return "COMPLETE_OUTPUT"

    if isinstance(receptors, (dict, list)) and len(receptors) == 0:
        return "BLOCKED_AT_RING7"

    return "PARTIAL_OUTPUT"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--species", required=True)
    args = ap.parse_args()

    root = Path("results/by_organism") / args.species

    if not root.is_dir():
        raise SystemExit("RESULT_DIRECTORY_MISSING")

    result = classify(root)

    print("SPECIES:", args.species)
    print("STATUS:", result)
    print("CLASSIFICATION_OK")


if __name__ == "__main__":
    main()
