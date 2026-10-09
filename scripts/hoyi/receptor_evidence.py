"""Curated receptor-evidence matcher for natural phage RBP candidates."""

import json
from pathlib import Path
from .rbp_aliases import load_aliases, resolve_alias


def load_evidence(path):
    path = Path(path)
    if not path.exists():
        return []

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    return data.get("records", [])


def _norm(x):
    return (x or "").strip().lower()


def match_receptor_evidence(candidate, evidence_records):
    """Strictly match one natural RBP candidate to curated receptor evidence.

    Matching priority:
    1. exact accession
    2. exact phage + exact protein name

    Broad host/genus/tail-fiber-name matching is intentionally forbidden.
    """

    input_accession = candidate.get("accession")

    alias_records = load_aliases(
        "data/antigens/natural_rbp_aliases.json"
    )
    alias_info = resolve_alias(
        input_accession,
        alias_records,
    )

    evidence_accession = (
        alias_info.get("canonical_accession")
        or input_accession
    )

    cand_acc = _norm(evidence_accession)
    cand_name = _norm(candidate.get("protein_name"))
    cand_org = _norm(candidate.get("source_organism"))

    # 1. accession exact
    if cand_acc:
        for ev in evidence_records:
            ev_acc = _norm(ev.get("accession"))
            if ev_acc and cand_acc == ev_acc:
                return {
                    "matched": True,
                    "match_type": "accession_exact",
                    "evidence_id": ev.get("evidence_id"),
                    "receptor_class": ev.get("receptor_class"),
                    "receptor_detail": ev.get("receptor_detail"),
                    "evidence_strength": ev.get("evidence_strength"),
                    "evidence_type": ev.get("evidence_type"),
                    "input_accession": input_accession,
                    "evidence_accession": evidence_accession,
                    "alias_resolution": alias_info,
                }

    # 2. exact phage + exact protein name
    for ev in evidence_records:
        ev_phage = _norm(ev.get("phage"))
        ev_name = _norm(ev.get("protein_name"))

        if (
            ev_phage
            and ev_name
            and cand_org == ev_phage
            and cand_name == ev_name
        ):
            return {
                "matched": True,
                "match_type": "phage_plus_protein_exact",
                "evidence_id": ev.get("evidence_id"),
                "receptor_class": ev.get("receptor_class"),
                "receptor_detail": ev.get("receptor_detail"),
                "evidence_strength": ev.get("evidence_strength"),
                "evidence_type": ev.get("evidence_type"),
            }

    return {
        "matched": False,
        "match_type": None,
        "evidence_id": None,
        "receptor_class": None,
        "receptor_detail": None,
        "evidence_strength": None,
        "evidence_type": None,
        "input_accession": input_accession,
        "evidence_accession": evidence_accession,
        "alias_resolution": alias_info,
    }
