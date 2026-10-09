"""Minimal cross-platform UniProt REST client for HOUYI."""

import json
import time
import urllib.parse
import urllib.request


BASE = "https://rest.uniprot.org"


def get_json(url, retries=3, timeout=30):
    headers = {
        "User-Agent": "HOUYI/1.0 protein-design-pipeline"
    }

    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception:
            if attempt + 1 >= retries:
                return None
            time.sleep(1.5 * (attempt + 1))

    return None


def search_uniprot(query, size=50, fields=None):
    if fields is None:
        fields = (
            "accession,protein_name,gene_names,"
            "organism_name,length,reviewed"
        )

    url = BASE + "/uniprotkb/search?" + urllib.parse.urlencode({
        "query": query,
        "fields": fields,
        "size": size,
        "format": "json",
    })

    data = get_json(url)
    return (data or {}).get("results", [])


def get_entry(accession):
    url = f"{BASE}/uniprotkb/{accession}?format=json"
    return get_json(url)


def get_sequence(accession):
    data = get_entry(accession)
    return (data or {}).get("sequence", {}).get("value", "")
