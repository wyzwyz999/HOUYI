#!/usr/bin/env python3
"""
Prepare an externally reviewed Ring7 input for HOUYI.

This tool does NOT discover, rank, or select biological targets.
It only validates a user-provided JSON list and writes it to the
expected Ring7 output path for downstream engineering tests.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="Reviewed Ring7 JSON file")
    ap.add_argument("--organism-slug", required=True, help="results/by_organism/<slug>")
    ap.add_argument("--root", default=".", help="HOUYI repo root")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    src = Path(args.input).resolve()

    if not src.is_file():
        print(f"APPROVED_INPUT_ERROR: file_not_found: {src}")
        return 2

    try:
        data = json.loads(src.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"APPROVED_INPUT_ERROR: invalid_json: {exc}")
        return 2

    if not isinstance(data, list):
        print("APPROVED_INPUT_ERROR: top_level_must_be_list")
        return 2

    if len(data) == 0:
        print("APPROVED_INPUT_ERROR: empty_list")
        return 3

    for i, item in enumerate(data):
        if not isinstance(item, dict):
            print(f"APPROVED_INPUT_ERROR: item_{i}_not_object")
            return 2

    out_dir = root / "results" / "by_organism" / args.organism_slug
    out_dir.mkdir(parents=True, exist_ok=True)

    out = out_dir / "ring7_fiber_targets.json"
    backup = None
    if out.exists():
        backup = out.with_suffix(".json.preapproved.bak")
        shutil.copy2(out, backup)

    out.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8"
    )

    print("APPROVED_INPUT_READY")
    print(f"RECORDS={len(data)}")
    print(f"OUTPUT={out}")
    if backup:
        print(f"BACKUP={backup}")
    print("DISCOVERY_PERFORMED=False")
    print("RANKING_PERFORMED=False")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
