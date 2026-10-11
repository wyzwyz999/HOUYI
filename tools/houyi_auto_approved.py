#!/usr/bin/env python3
"""
HOUYI pre-approved auto gate.

Engineering-only approval gate:
- does not discover or rank biological targets
- verifies an already-reviewed Ring7 JSON against a pre-approved allowlist
- if approved, installs Ring7 JSON and can launch Ring8-10
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


def die(msg: str, code: int = 2):
    print(f"AUTO_GATE_BLOCKED: {msg}")
    raise SystemExit(code)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--whitelist", required=True)
    ap.add_argument("--input", required=True, help="Reviewed Ring7 JSON list")
    ap.add_argument("--organism", required=True, help="Display organism name")
    ap.add_argument("--organism-slug", required=True)
    ap.add_argument("--root", default=".")
    ap.add_argument("--run", action="store_true", help="Launch Ring8-10 after approval")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    wl_path = Path(args.whitelist).resolve()
    input_path = Path(args.input).resolve()

    if not wl_path.is_file():
        die(f"whitelist_not_found: {wl_path}")
    if not input_path.is_file():
        die(f"input_not_found: {input_path}")

    try:
        wl = json.loads(wl_path.read_text(encoding="utf-8"))
        data = json.loads(input_path.read_text(encoding="utf-8"))
    except Exception as exc:
        die(f"invalid_json: {exc}")

    if not isinstance(wl, dict):
        die("whitelist_top_level_not_object")
    if not isinstance(data, list) or not data:
        die("input_must_be_nonempty_list")

    approved = wl.get("approved_organisms", {})
    org_cfg = approved.get(args.organism_slug)
    if not isinstance(org_cfg, dict):
        die(f"organism_not_preapproved: {args.organism_slug}")

    if org_cfg.get("organism") != args.organism:
        die(
            f"organism_name_mismatch: whitelist={org_cfg.get('organism')!r} "
            f"input={args.organism!r}"
        )

    allowed_targets = set(org_cfg.get("fiber_targets", []))
    if not allowed_targets:
        die("no_preapproved_targets")

    seen = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            die(f"item_{i}_not_object")
        target = item.get("fiber_target")
        if not target:
            die(f"item_{i}_missing_fiber_target")
        if target not in allowed_targets:
            die(f"target_not_preapproved: {target}")
        seen.append(target)

    out_dir = root / "results" / "by_organism" / args.organism_slug
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "ring7_fiber_targets.json"

    if out.exists():
        backup = out.with_suffix(".json.pre_auto_gate.bak")
        shutil.copy2(out, backup)
        print(f"BACKUP={backup}")

    out.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8"
    )

    print("AUTO_GATE_APPROVED")
    print(f"ORGANISM={args.organism}")
    print(f"TARGETS={len(seen)}")
    print(f"OUTPUT={out}")
    print("DISCOVERY_PERFORMED=False")
    print("RANKING_PERFORMED=False")

    if not args.run:
        print("PIPELINE_NOT_STARTED")
        return 0

    cmd = [
        sys.executable,
        str(root / "scripts" / "pipeline.py"),
        "--organism", args.organism,
        "--start", "8",
        "--stop", "10",
    ]
    print("PIPELINE_STARTING")
    return subprocess.run(cmd, cwd=str(root)).returncode


if __name__ == "__main__":
    raise SystemExit(main())
