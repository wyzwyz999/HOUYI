#!/usr/bin/env python3
"""通用数据质量状态管理，不参与候选筛选。"""

import argparse
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

STATUSES = {
    "COMPLETE",
    "REQUEST_ERROR",
    "INCOMPLETE_DATA",
    "NO_VALID_CANDIDATE",
}


def save_state(path, status, total=None, retrieved=None, detail=""):
    if status not in STATUSES:
        raise ValueError("INVALID_STATUS")

    if total is not None and (not isinstance(total, int) or total < 0):
        raise ValueError("INVALID_TOTAL")

    if retrieved is not None and (
        not isinstance(retrieved, int) or retrieved < 0
    ):
        raise ValueError("INVALID_RETRIEVED")

    report = {
        "schema_version": "1.0",
        "status": status,
        "total": total,
        "retrieved": retrieved,
        "detail": detail,
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
    }

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    fd, temp_path = tempfile.mkstemp(
        prefix=".data_quality_",
        suffix=".tmp",
        dir=target.parent,
    )

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())

        os.replace(temp_path, target)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)

    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--status", required=True, choices=sorted(STATUSES))
    parser.add_argument("--total", type=int)
    parser.add_argument("--retrieved", type=int)
    parser.add_argument("--detail", default="")
    args = parser.parse_args()

    result = save_state(
        args.output,
        args.status,
        args.total,
        args.retrieved,
        args.detail,
    )
    print("STATUS:", result["status"])
    print("DATA_QUALITY_STATE_SAVED")
