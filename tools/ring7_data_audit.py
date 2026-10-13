import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import requests


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--organism", required=True)
    parser.add_argument("--retrieved", type=int, required=True)
    args = parser.parse_args()

    url = "https://rest.uniprot.org/uniprotkb/search"
    query = f'organism_name:"{args.organism}" AND reviewed:true'

    report = {
        "organism": args.organism,
        "source": "UniProtKB reviewed",
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "retrieved": args.retrieved,
        "total": None,
        "coverage": None,
        "status": "REQUEST_ERROR",
    }

    try:
        response = requests.get(
            url,
            params={"query": query, "size": 1, "format": "json"},
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()

        if not isinstance(data, dict) or not isinstance(data.get("results"), list):
            raise ValueError("INVALID_RESPONSE_FORMAT")

        total = int(response.headers["x-total-results"])

        report["total"] = total
        report["coverage"] = round(args.retrieved / total, 4) if total else None

        if args.retrieved > total:
            report["status"] = "COUNT_MISMATCH"
        elif args.retrieved < total:
            report["status"] = "INCOMPLETE"
        else:
            report["status"] = "COMPLETE"

    except Exception as exc:
        report["error_type"] = type(exc).__name__
        report["error"] = str(exc)

    out = Path("/root/autodl-tmp/HOUYI_archives")
    out.mkdir(parents=True, exist_ok=True)

    slug = args.organism.lower().replace(" ", "_")
    path = out / f"{slug}_ring7_data_audit.json"

    path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("STATUS:", report["status"])
    print("TOTAL:", report["total"])
    print("RETRIEVED:", report["retrieved"])
    print("COVERAGE:", report["coverage"])
    print("REPORT:", path)
    print("RING7_DATA_AUDIT_OK")


if __name__ == "__main__":
    main()
