#!/usr/bin/env python3
"""HOUYI read-only result audit export."""

import argparse
import json
import zipfile
from pathlib import Path
from datetime import datetime, timezone


def load_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--species", required=True)
    ap.add_argument("--root", default="results/by_organism")
    ap.add_argument("--out", default="/root/autodl-tmp/HOUYI_archives")
    args = ap.parse_args()

    source = Path(args.root) / args.species
    if not source.is_dir():
        raise SystemExit(f"Missing results: {source}")

    state = load_json(source / "pipeline_state.json") or {}
    nano = load_json(source / "nanosyringes.json")

    if not isinstance(nano, list):
        nano = []

    complete = sum(
        x.get("complete") is True
        for x in nano
        if isinstance(x, dict)
    )

    status = (
        "COMPLETE_OUTPUT"
        if nano and complete == len(nano)
        else "PARTIAL_OUTPUT"
    )

    report = {
        "schema_version": "1.0",
        "species": args.species,
        "organism": state.get("organism"),
        "audit_time_utc": datetime.now(timezone.utc).isoformat(),
        "result_status": status,
        "ring_execution_status": {
            str(i): (
                state.get("rings", {})
                .get(str(i), {})
                .get("status", "UNKNOWN")
            )
            for i in range(1, 11)
        },
        "nanosyringe_records": len(nano),
        "nanosyringe_complete": complete,
        "note": (
            "Computational output completeness only; "
            "not evidence of antimicrobial activity."
        ),
    }

    output_dir = Path(args.out)
    output_dir.mkdir(parents=True, exist_ok=True)

    report_path = output_dir / f"{args.species}_audit.json"
    zip_path = output_dir / f"{args.species}_audit_bundle.zip"

    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    with zipfile.ZipFile(
        zip_path, "w", zipfile.ZIP_DEFLATED
    ) as z:
        z.write(report_path, report_path.name)

        for f in source.rglob("*"):
            if f.is_file():
                z.write(
                    f,
                    str(Path(args.species) / f.relative_to(source))
                )

    with zipfile.ZipFile(zip_path) as z:
        damaged = z.testzip()
        if damaged:
            raise SystemExit(f"ZIP ERROR: {damaged}")

    print("RESULT_STATUS:", status)
    print("COMPLETE:", f"{complete}/{len(nano)}")
    print("REPORT:", report_path)
    print("ZIP:", zip_path)
    print("EXPORT_OK")


if __name__ == "__main__":
    main()
