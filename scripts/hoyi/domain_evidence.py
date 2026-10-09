"""Domain-evidence annotation for natural RBP candidates.

This module extracts public annotation evidence only.
It does NOT decide whether a domain is graftable.
"""

from .uniprot_client import get_entry
from .rbp_aliases import load_aliases, resolve_alias


DOMAIN_FEATURE_TYPES = {
    "Domain",
    "Region",
    "Repeat",
    "Coiled coil",
    "Motif",
    "Chain",
}

DOMAIN_DBS = {
    "InterPro",
    "Pfam",
    "Gene3D",
    "SUPFAM",
    "PDB",
    "AlphaFoldDB",
}


def _loc_value(obj):
    if not isinstance(obj, dict):
        return None
    value = obj.get("value")
    return int(value) if isinstance(value, int) else value


def extract_domain_evidence(accession):
    """Extract domain-boundary and structure annotation from UniProt.

    Alias resolution is used only for evidence lookup.
    The original accession is preserved for traceability.
    """

    alias_records = load_aliases(
        "data/antigens/natural_rbp_aliases.json"
    )

    alias_info = resolve_alias(accession, alias_records)

    evidence_accession = (
        alias_info.get("canonical_accession")
        or accession
    )

    d = get_entry(evidence_accession) or {}

    domains = []

    for f in d.get("features", []):
        ftype = f.get("type")
        if ftype not in DOMAIN_FEATURE_TYPES:
            continue

        loc = f.get("location") or {}
        start = _loc_value(loc.get("start"))
        end = _loc_value(loc.get("end"))

        domains.append({
            "feature_type": ftype,
            "description": f.get("description"),
            "start": start,
            "end": end,
            "length": (
                end - start + 1
                if isinstance(start, int) and isinstance(end, int)
                else None
            ),
            "evidence_source": "UniProt_feature",
        })

    crossrefs = []

    for x in d.get("uniProtKBCrossReferences", []):
        db = x.get("database")
        if db not in DOMAIN_DBS:
            continue

        crossrefs.append({
            "database": db,
            "id": x.get("id"),
            "properties": x.get("properties") or [],
        })

    has_boundary = any(
        isinstance(x.get("start"), int)
        and isinstance(x.get("end"), int)
        for x in domains
    )

    return {
        "accession": accession,
        "input_accession": accession,
        "evidence_accession": evidence_accession,
        "alias_resolution": alias_info,
        "domain_boundary_confirmed": has_boundary,
        "domains": domains,
        "crossrefs": crossrefs,

        # IMPORTANT:
        # domain boundary != proven receptor-binding domain
        # != proven graftable domain
        "receptor_binding_domain_confirmed": False,
        "graftable_domain_confirmed": False,
    }
