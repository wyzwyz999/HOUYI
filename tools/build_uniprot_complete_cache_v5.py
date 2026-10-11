#!/usr/bin/env python3
"""
Generic UniProt paginated cache builder (curl-backed).

- Fetches UniProt pages by following Link: rel="next"
- Records COMPLETE / INCOMPLETE_DATA / REQUEST_ERROR
- Saves one atomic local JSON cache
- Does not perform receptor inference, ranking, or Ring7 integration
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

API = "https://rest.uniprot.org/uniprotkb/search"
DEFAULT_FIELDS = "accession,gene_names,protein_name,length,cc_function,organism_name"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def build_first_url(query: str, fields: str, page_size: int) -> str:
    params = {
        "query": query,
        "fields": fields,
        "size": page_size,
        "format": "json",
    }
    return API + "?" + urllib.parse.urlencode(params)


def parse_header_blocks(text: str) -> Dict[str, str]:
    """
    Robust curl-header parser.

    Do not depend on HTTP block separation because proxies / HTTP2 / -L can
    produce header dumps whose blank-line layout differs across environments.
    Instead scan the entire dump and keep the last occurrence of each header.
    """
    headers: Dict[str, str] = {}

    link_matches = re.findall(
        r"(?im)^link:\s*(.+?)\s*$",
        text,
    )
    if link_matches:
        headers["link"] = link_matches[-1].strip()

    total_matches = re.findall(
        r"(?im)^x-total-results:\s*(\d+)\s*$",
        text,
    )
    if total_matches:
        headers["x-total-results"] = total_matches[-1].strip()

    return headers


def parse_next_link(link_header: Optional[str]) -> Optional[str]:
    if not link_header:
        return None

    # IMPORTANT:
    # UniProt next URLs may themselves contain commas (e.g. fields=a,b,c).
    # Therefore NEVER split the Link header on commas before extracting the URL.
    m = re.search(
        r"<([^>]+)>\s*;\s*rel\s*=\s*[\"']?next[\"']?",
        link_header,
        flags=re.I,
    )
    return m.group(1) if m else None


def curl_json(url: str, timeout: int = 30) -> Tuple[Dict[str, Any], Dict[str, str], int]:
    """
    Use the exact transport pattern already verified manually on AutoDL:
    curl -D - prints response headers to stdout, while -o writes JSON body
    to a temporary file. This avoids environment-specific header-file parsing.
    """
    curl_bin = shutil.which("curl") or shutil.which("curl.exe")
    if not curl_bin:
        raise RuntimeError("CURL_NOT_FOUND")

    with tempfile.TemporaryDirectory(prefix="houyi_uniprot_") as td:
        td = Path(td)
        body_file = td / "body.json"

        cmd = [
            curl_bin,
            "-sS",
            "-L",
            "--max-time", str(timeout),
            "-A", "HOUYI-generic-cache/5.0",
            "-D", "-",
            "-o", str(body_file),
            "-w", "\n__HOUYI_HTTP_CODE__=%{http_code}\n",
            url,
        ]

        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

        stdout = r.stdout or ""
        m_code = re.search(r"__HOUYI_HTTP_CODE__=(\d+)", stdout)
        status = int(m_code.group(1)) if m_code else 0

        # Remove our trailer before parsing headers.
        header_text = re.sub(
            r"\n?__HOUYI_HTTP_CODE__=\d+\s*$",
            "",
            stdout,
        )

        headers: Dict[str, str] = {}
        for line in header_text.splitlines():
            line = line.strip()
            if not line or ":" not in line:
                continue
            key, value = line.split(":", 1)
            key = key.strip().lower()
            if key in {"link", "x-total-results"}:
                headers[key] = value.strip()

        body_text = (
            body_file.read_text(encoding="utf-8", errors="replace")
            if body_file.exists()
            else ""
        )

        if r.returncode != 0:
            raise RuntimeError(f"CURL_FAILED_{r.returncode}")
        if status != 200:
            raise RuntimeError(f"HTTP_{status}")

        try:
            data = json.loads(body_text)
        except Exception as exc:
            raise ValueError(f"UNIPROT_INVALID_JSON: {exc}") from exc

        if not isinstance(data, dict):
            raise ValueError("UNIPROT_INVALID_RESPONSE")

        return data, headers, status

def deduplicate(records: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], int]:
    seen = set()
    unique = []
    duplicates = 0
    for record in records:
        acc = record.get("primaryAccession")
        key = acc if acc else json.dumps(record, sort_keys=True, ensure_ascii=False)
        if key in seen:
            duplicates += 1
            continue
        seen.add(key)
        unique.append(record)
    return unique, duplicates


def atomic_json_dump(obj: Dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=output.name + ".", suffix=".tmp", dir=str(output.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp, output)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def fetch_all(
    query: str,
    fields: str,
    page_size: int,
    max_pages: int,
    timeout: int,
    pause_seconds: float,
) -> Dict[str, Any]:
    next_url: Optional[str] = build_first_url(query, fields, page_size)
    all_records: List[Dict[str, Any]] = []
    page_summaries: List[Dict[str, Any]] = []
    reported_total: Optional[int] = None
    pages_fetched = 0
    error: Optional[str] = None

    try:
        while next_url and pages_fetched < max_pages:
            data, headers, _ = curl_json(next_url, timeout=timeout)
            results = data.get("results")
            if not isinstance(results, list):
                raise ValueError("UNIPROT_INVALID_RESULTS")

            pages_fetched += 1
            all_records.extend(results)

            if reported_total is None:
                raw_total = headers.get("x-total-results")
                if raw_total and raw_total.isdigit():
                    reported_total = int(raw_total)

            following = parse_next_link(headers.get("link"))
            page_summaries.append({
                "page": pages_fetched,
                "records": len(results),
                "has_next": bool(following),
            })
            next_url = following

            if next_url and pages_fetched < max_pages and pause_seconds > 0:
                time.sleep(pause_seconds)

    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"

    unique_records, duplicate_count = deduplicate(all_records)

    if error:
        status = "REQUEST_ERROR"
    elif next_url:
        status = "INCOMPLETE_DATA"
    elif reported_total is not None and len(unique_records) < reported_total:
        status = "INCOMPLETE_DATA"
    else:
        status = "COMPLETE"

    return {
        "source": "UniProt REST API",
        "transport": "curl",
        "query": query,
        "fields": fields,
        "timestamp_utc": utc_now(),
        "page_size": page_size,
        "max_pages": max_pages,
        "pages_fetched": pages_fetched,
        "records_fetched": len(all_records),
        "unique_records": len(unique_records),
        "duplicate_records": duplicate_count,
        "reported_total": reported_total,
        "has_more_pages": bool(next_url),
        "status": status,
        "error": error,
        "page_summaries": page_summaries,
        "ring7_integrated": False,
        "note": "Generic completeness/cache layer only; no receptor inference or candidate ranking.",
        "records": unique_records,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--query",
        default="organism_id:9606 AND reviewed:true",
        help="UniProt query; default is reviewed human proteins for benign testing.",
    )
    ap.add_argument("--fields", default=DEFAULT_FIELDS)
    ap.add_argument("--page-size", type=int, default=100)
    ap.add_argument("--max-pages", type=int, default=5)
    ap.add_argument("--timeout", type=int, default=30)
    ap.add_argument("--pause-seconds", type=float, default=0.2)
    ap.add_argument("--output", default="results/data_cache/uniprot/generic_cache.json")
    args = ap.parse_args()

    if not (1 <= args.page_size <= 500):
        raise SystemExit("--page-size must be between 1 and 500")
    if args.max_pages < 1:
        raise SystemExit("--max-pages must be >= 1")

    result = fetch_all(
        query=args.query,
        fields=args.fields,
        page_size=args.page_size,
        max_pages=args.max_pages,
        timeout=args.timeout,
        pause_seconds=args.pause_seconds,
    )
    output = Path(args.output)
    atomic_json_dump(result, output)

    print(f"STATUS={result['status']}")
    print(f"PAGES_FETCHED={result['pages_fetched']}")
    print(f"UNIQUE_RECORDS={result['unique_records']}")
    print(f"REPORTED_TOTAL={result['reported_total']}")
    print(f"HAS_MORE_PAGES={result['has_more_pages']}")
    print(f"ERROR={result['error']}")
    print(f"OUTPUT={output}")

    if result["status"] == "REQUEST_ERROR":
        return 2
    if result["status"] == "INCOMPLETE_DATA":
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
