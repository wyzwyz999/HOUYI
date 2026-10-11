#!/usr/bin/env python3
"""
Validate a generic UniProt cache before any downstream consumer reads it.

This is a data-integrity gate only.
It does not perform receptor inference, ranking, or biological target selection.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


REQUIRED_STATUSES = {"COMPLETE", "INCOMPLETE_DATA", "REQUEST_ERROR"}


def fail(msg: str, code: int = 2) -> None:
    print(f"CACHE_REJECTED: {msg}")
    raise SystemExit(code)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cache", help="Path to cache JSON")
    ap.add_argument(
        "--require-complete",
        action="store_true",
        help="Reject unless status is COMPLETE",
    )
    args = ap.parse_args()

    p = Path(args.cache)
    if not p.is_file():
        fail(f"file_not_found: {p}")

    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        fail(f"invalid_json: {exc}")

    if not isinstance(d, dict):
        fail("top_level_not_object")

    status = d.get("status")
    if status not in REQUIRED_STATUSES:
        fail(f"invalid_status: {status!r}")

    records = d.get("records")
    if not isinstance(records, list):
        fail("records_not_list")

    unique_records = d.get("unique_records")
    records_fetched = d.get("records_fetched")
    duplicate_records = d.get("duplicate_records")
    reported_total = d.get("reported_total")
    has_more_pages = d.get("has_more_pages")
    error = d.get("error")

    for name, value in (
        ("unique_records", unique_records),
        ("records_fetched", records_fetched),
        ("duplicate_records", duplicate_records),
    ):
        if not isinstance(value, int) or value < 0:
            fail(f"invalid_{name}: {value!r}")

    if unique_records != len(records):
        fail(
            f"unique_records_mismatch: metadata={unique_records} "
            f"actual={len(records)}"
        )

    if records_fetched < unique_records:
        fail(
            f"records_fetched_lt_unique: fetched={records_fetched} "
            f"unique={unique_records}"
        )

    if reported_total is not None:
        if not isinstance(reported_total, int) or reported_total < 0:
            fail(f"invalid_reported_total: {reported_total!r}")

    if not isinstance(has_more_pages, bool):
        fail(f"invalid_has_more_pages: {has_more_pages!r}")

    if status == "REQUEST_ERROR" and not error:
        fail("request_error_without_error_message")

    if status == "COMPLETE":
        if error:
            fail(f"complete_with_error: {error}")
        if has_more_pages:
            fail("complete_but_has_more_pages")
        if reported_total is not None and unique_records < reported_total:
            fail(
                f"complete_but_count_incomplete: unique={unique_records} "
                f"reported_total={reported_total}"
            )

    if args.require_complete and status != "COMPLETE":
        fail(f"status_is_{status}_not_COMPLETE", code=3)

    print(f"CACHE_ACCEPTED: status={status}")
    print(f"UNIQUE_RECORDS={unique_records}")
    print(f"REPORTED_TOTAL={reported_total}")
    print(f"HAS_MORE_PAGES={has_more_pages}")
    print(f"RING7_INTEGRATED={d.get('ring7_integrated')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
