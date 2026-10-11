#!/usr/bin/env python3
"""Standalone UniProtKB pagination/data-quality auditor. Not part of HOUYI design."""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

API = 'https://rest.uniprot.org/uniprotkb/search'


def fetch(query, page_size=100, max_pages=3, timeout=30):
    if not 1 <= page_size <= 500 or max_pages < 1 or timeout <= 0:
        raise ValueError('Invalid page-size, max-pages or timeout')
    params = {'query': query, 'size': page_size, 'fields': 'accession', 'format': 'json'}
    url = API
    pages = 0
    retrieved = 0
    ids = set()
    duplicates = 0
    total = None
    error = None
    history = []
    with requests.Session() as session:
        while url is not None and pages < max_pages:
            try:
                parsed = urlparse(url)
                if parsed.scheme != 'https' or parsed.netloc != 'rest.uniprot.org' or parsed.path != '/uniprotkb/search':
                    raise ValueError('Unexpected pagination URL')
                response = session.get(url, params=params, timeout=timeout)
                response.raise_for_status()
                body = response.json()
                if not isinstance(body, dict) or not isinstance(body.get('results'), list):
                    raise ValueError('Invalid UniProt result structure')
                if total is None:
                    header = response.headers.get('x-total-results')
                    total = int(header) if header is not None else None
                batch = body['results']
                for record in batch:
                    if not isinstance(record, dict) or not record.get('primaryAccession'):
                        raise ValueError('Missing primaryAccession')
                    accession = record['primaryAccession']
                    retrieved += 1
                    if accession in ids:
                        duplicates += 1
                    ids.add(accession)
                pages += 1
                history.append({'page': pages, 'record_count': len(batch)})
                url = response.links.get('next', {}).get('url')
                params = None
            except (requests.RequestException, ValueError, TypeError) as exc:
                error = f'{type(exc).__name__}: {exc}'
                break
    if error:
        status = 'REQUEST_ERROR'
    elif duplicates:
        status = 'DUPLICATE_RECORDS'
    elif url is not None or total is None or len(ids) < total:
        status = 'INCOMPLETE_DATA'
    elif len(ids) > total:
        status = 'COUNT_MISMATCH'
    else:
        status = 'COMPLETE'
    return {
        'schema_version': '1.0', 'source': 'UniProtKB', 'query': query,
        'checked_at_utc': datetime.now(timezone.utc).isoformat(),
        'page_size': page_size, 'max_pages': max_pages,
        'pages_fetched': pages, 'records_fetched': retrieved,
        'unique_records': len(ids), 'duplicate_records': duplicates,
        'reported_total': total, 'has_more_pages': url is not None,
        'status': status, 'error': error, 'page_summary': history,
        'ring7_integrated': False,
        'note': 'Standalone data-quality audit; no candidate or receptor inference.',
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--query', default='reviewed:true AND organism_id:9606')
    p.add_argument('--page-size', type=int, default=5)
    p.add_argument('--max-pages', type=int, default=3)
    p.add_argument('--timeout', type=float, default=30)
    p.add_argument('--output', default='/root/autodl-tmp/HOUYI_archives/uniprot_client_acceptance.json')
    args = p.parse_args()
    report = fetch(args.query, args.page_size, args.max_pages, args.timeout)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print('PAGES_FETCHED:', report['pages_fetched'])
    print('UNIQUE_RECORDS:', report['unique_records'])
    print('STATUS:', report['status'])
    print('REPORT:', output)
    print('UNIPROT_CLIENT_REPORT_SAVED')
    if report['status'] == 'REQUEST_ERROR':
        print('ERROR:', report['error'], file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
