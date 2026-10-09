"""Unified evidence summary for natural RBP candidates.

Pure aggregation only:
- no network calls
- no automatic READY promotion
"""

def summarize_rbp_evidence(
    candidate,
    receptor_evidence=None,
    domain_evidence=None,
):
    receptor_evidence = receptor_evidence or {}
    domain_evidence = domain_evidence or {}

    protein_name = (candidate.get("protein_name") or "").lower()

    protein_rbp_confirmed = (
        "receptor binding protein" in protein_name
        or "receptor-binding protein" in protein_name
    )

    receptor_strength = receptor_evidence.get("evidence_strength")

    domain_boundary_confirmed = bool(
        domain_evidence.get("domain_boundary_confirmed", False)
    )

    receptor_binding_domain_confirmed = bool(
        domain_evidence.get(
            "receptor_binding_domain_confirmed",
            False,
        )
    )

    graftable_domain_confirmed = bool(
        domain_evidence.get(
            "graftable_domain_confirmed",
            False,
        )
    )

    if receptor_binding_domain_confirmed:
        rbd_domain_evidence_strength = "high"
    elif domain_boundary_confirmed:
        rbd_domain_evidence_strength = "boundary_only"
    else:
        rbd_domain_evidence_strength = "none"

    # Conservative gate:
    # evidence summary itself never upgrades candidates to READY
    ready_for_ring9 = (
        protein_rbp_confirmed
        and receptor_strength in ("high", "medium")
        and receptor_binding_domain_confirmed
        and graftable_domain_confirmed
    )

    return {
        "accession": candidate.get("accession"),
        "protein_name": candidate.get("protein_name"),
        "source_organism": candidate.get("source_organism"),

        "protein_rbp_confirmed": protein_rbp_confirmed,

        "receptor_evidence_matched": bool(
            receptor_evidence.get("matched", False)
        ),
        "receptor_class": receptor_evidence.get("receptor_class"),
        "receptor_evidence_strength": receptor_strength,

        "domain_boundary_confirmed": domain_boundary_confirmed,
        "rbd_domain_evidence_strength": rbd_domain_evidence_strength,
        "receptor_binding_domain_confirmed": (
            receptor_binding_domain_confirmed
        ),
        "graftable_domain_confirmed": graftable_domain_confirmed,

        "ready_for_ring9": ready_for_ring9,
    }
