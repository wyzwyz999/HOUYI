#!/usr/bin/env python3
"""
HOUYI generic preflight launcher.

Checks a local UniProt cache with tools/houyi_data_ready.py.
Only if DATA_READY, launches the requested pipeline command.

Engineering wrapper only:
- no receptor inference
- no candidate ranking
- no biological target selection
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", required=True, help="UniProt cache JSON")
    ap.add_argument(
        "pipeline_args",
        nargs=argparse.REMAINDER,
        help="Arguments passed to scripts/pipeline.py after --",
    )
    args = ap.parse_args()

    root = Path(__file__).resolve().parents[1]
    gate = root / "tools" / "houyi_data_ready.py"
    pipeline = root / "scripts" / "pipeline.py"

    if not gate.is_file():
        print(f"PREFLIGHT_ERROR: missing gate: {gate}")
        return 2
    if not pipeline.is_file():
        print(f"PREFLIGHT_ERROR: missing pipeline: {pipeline}")
        return 2

    gate_cmd = [sys.executable, str(gate), args.cache]
    gate_run = subprocess.run(gate_cmd)
    if gate_run.returncode != 0:
        print("PREFLIGHT_BLOCKED")
        return gate_run.returncode

    pipeline_args = list(args.pipeline_args)
    if pipeline_args and pipeline_args[0] == "--":
        pipeline_args = pipeline_args[1:]

    if not pipeline_args:
        print("PREFLIGHT_READY")
        print("PIPELINE_NOT_STARTED: no pipeline arguments supplied")
        return 0

    print("PREFLIGHT_READY")
    print("PIPELINE_STARTING")
    return subprocess.run(
        [sys.executable, str(pipeline), *pipeline_args],
        cwd=str(root),
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
