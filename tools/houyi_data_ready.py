#!/usr/bin/env python3
"""
Generic HOUYI data-readiness gate.

Checks only whether a UniProt cache is structurally valid and COMPLETE.
Does not inspect biological targets, perform ranking, or run Ring7.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cache", help="Path to UniProt cache JSON")
    args = ap.parse_args()

    p = Path(args.cache)
    if not p.is_file():
        print(f"DATA_BLOCKED: cache_not_found: {p}")
        return 2

    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"DATA_BLOCKED: invalid_json: {exc}")
        return 2

    if not isinstance(d, dict):
        print("DATA_BLOCKED: top_level_not_object")
        return 2

    status = d.get("status")
    unique_records = d.get("unique_records")
    reported_total = d.get("reported_total")
    has_more_pages = d.get("has_more_pages")
    error = d.get("error")

    if status != "COMPLETE":
        print(f"DATA_BLOCKED: status={status}")
        if error:
            print(f"ERROR={error}")
        return 3

    if has_more_pages is not False:
        print("DATA_BLOCKED: complete_but_has_more_pages")
        return 3

    if not isinstance(unique_records, int) or unique_records < 0:
        print("DATA_BLOCKED: invalid_unique_records")
        return 2

    if reported_total is not None:
        if not isinstance(reported_total, int) or reported_total < 0:
            print("DATA_BLOCKED: invalid_reported_total")
            return 2
        if unique_records < reported_total:
            print(
                f"DATA_BLOCKED: count_incomplete "
                f"unique={unique_records} reported_total={reported_total}"
            )
            return 3

    print("DATA_READY")
    print(f"UNIQUE_RECORDS={unique_records}")
    print(f"REPORTED_TOTAL={reported_total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
