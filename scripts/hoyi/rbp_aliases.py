"""Strict accession-alias handling for natural RBP evidence."""

import json
from pathlib import Path


def load_aliases(path):
    path = Path(path)
    if not path.exists():
        return []

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    return data.get("records", [])


def resolve_alias(accession, alias_records):
    acc = (accession or "").strip()

    if not acc:
        return {
            "matched": False,
            "input_accession": accession,
            "canonical_accession": None,
            "equivalence_type": None,
            "alias_id": None,
        }

    for rec in alias_records:
        canonical = rec.get("canonical_accession")
        equivalents = rec.get("equivalent_accessions") or []

        if acc == canonical or acc in equivalents:
            return {
                "matched": True,
                "input_accession": acc,
                "canonical_accession": canonical,
                "equivalence_type": rec.get("equivalence_type"),
                "sequence_identity": rec.get("sequence_identity"),
                "alias_id": rec.get("alias_id"),
            }

    return {
        "matched": False,
        "input_accession": acc,
        "canonical_accession": acc,
        "equivalence_type": None,
        "alias_id": None,
    }
