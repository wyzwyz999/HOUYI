"""Natural phage tail-fiber / RBP candidate discovery for HOUYI.

This module is Discovery-mode only.
It does not read retrospective wet-lab benchmark data.
"""

from .uniprot_client import search_uniprot, get_sequence
from .receptor_evidence import load_evidence, match_receptor_evidence
from .domain_evidence import extract_domain_evidence
from .rbp_evidence_summary import summarize_rbp_evidence


POSITIVE_TERMS = [
    "tail fiber",
    "tail fibre",
    "receptor-binding protein",
    "receptor binding protein",
    "host recognition",
    "adsorption protein",
]

NEGATIVE_TERMS = [
    "capsid",
    "terminase",
    "portal protein",
    "DNA polymerase",
    "integrase",
]


def _protein_name(result):
    pd = result.get("proteinDescription", {})

    if "recommendedName" in pd:
        return (
            pd["recommendedName"]
            .get("fullName", {})
            .get("value", "")
        )

    names = pd.get("submissionNames", [])
    if names:
        return names[0].get("fullName", {}).get("value", "")

    return ""


def _organism_name(result):
    return (
        result.get("organism", {})
        .get("scientificName", "")
    )


def _is_reviewed(result):
    return result.get("entryType") == "UniProtKB reviewed (Swiss-Prot)"


def _score_candidate(name, reviewed, length, source_organism="", host_organism=""):
    text = (name or "").lower()
    src = (source_organism or "").lower()
    host = (host_organism or "").lower()

    score = 0.0
    matched_terms = []
    evidence = {
        "phage_context": "unknown",
        "host_relevance": "unknown",
        "annotation_confidence": "standard",
    }

    for term in POSITIVE_TERMS:
        if term.lower() in text:
            # 显式RBP注释优先于泛化tail-fiber注释。
            if term.lower() in (
                "receptor-binding protein",
                "receptor binding protein",
            ):
                score += 4.0
            elif term.lower() == "host recognition":
                score += 3.0
            else:
                score += 2.0

            matched_terms.append(term)

    for term in NEGATIVE_TERMS:
        if term.lower() in text:
            return -999.0, matched_terms, {
                "phage_context": "rejected",
                "host_relevance": "rejected",
                "annotation_confidence": "rejected",
            }

    # 明确噬菌体来源优先。
    if "phage" in src:
        score += 2.0
        evidence["phage_context"] = "explicit_phage"

        genus = (host_organism or "").split()[0].lower() if host_organism else ""
        if genus and genus in src:
            score += 1.0
            evidence["host_relevance"] = "host_genus_match"
        else:
            evidence["host_relevance"] = "phage_no_explicit_host_match"

    # 宿主基因组中的putative phage protein，作为次级证据保留。
    elif host and host in src:
        score += 0.5
        evidence["phage_context"] = "host_genome_possible_prophage"
        evidence["host_relevance"] = "host_match"

    if "putative" in text:
        score -= 0.5
        evidence["annotation_confidence"] = "putative"

    if reviewed:
        score += 1.0
        evidence["annotation_confidence"] = "reviewed"

    if 100 <= length <= 2000:
        score += 0.5

    return score, matched_terms, evidence


def search_natural_rbps(
    host_organism,
    size=100,
    top_n=10,
    fetch_sequences=True,
    annotate_domains=False,
):
    """Search annotated natural phage RBP/tail-fiber candidates.

    host_organism is used as a discovery term only.
    Wet-lab benchmark data are never read here.
    """

    # Broad annotation-level discovery.
    # We deliberately do not hard-code a known experimental fiber.
    queries = [
        f'"tail fiber" AND "{host_organism}"',
        f'"tail fibre" AND "{host_organism}"',
        f'"receptor-binding protein" AND "{host_organism}"',
        f'"host recognition" AND "{host_organism}"',
    ]

    evidence_records = load_evidence(
        "data/antigens/natural_rbp_receptor_evidence.json"
    )

    merged = {}

    for query in queries:
        for r in search_uniprot(query, size=size):
            accession = r.get("primaryAccession")
            if accession:
                merged[accession] = r

    candidates = []

    for accession, r in merged.items():
        name = _protein_name(r)
        length = (r.get("sequence") or {}).get("length", 0)
        reviewed = _is_reviewed(r)

        source_organism = _organism_name(r)

        score, matched_terms, evidence = _score_candidate(
            name=name,
            reviewed=reviewed,
            length=length,
            source_organism=source_organism,
            host_organism=host_organism,
        )

        if score <= 0:
            continue

        seq = ""
        if fetch_sequences:
            seq = get_sequence(accession)

        receptor_evidence = match_receptor_evidence(
            {
                "accession": accession,
                "protein_name": name,
                "source_organism": source_organism,
            },
            evidence_records,
        )

        candidates.append({
            "accession": accession,
            "protein_name": name,
            "source_organism": source_organism,
            "sequence": seq,
            "length": len(seq) if seq else length,
            "reviewed": reviewed,
            "matched_terms": matched_terms,
            "natural_rbp_score": score,
            "phage_context": evidence["phage_context"],
            "host_relevance": evidence["host_relevance"],
            "annotation_confidence": evidence["annotation_confidence"],
            "receptor_evidence": receptor_evidence,
            "source": "UniProt",
            "route": "natural",
        })

    # 稳定排序：分数相同时使用明确证据字段和accession作为tie-break，
    # 避免依赖UniProt返回顺序。
    candidates.sort(
        key=lambda x: (
            -x["natural_rbp_score"],
            -int(x.get("phage_context") == "explicit_phage"),
            -int(x.get("host_relevance") == "host_genus_match"),
            -int(bool(x.get("sequence"))),
            -int(bool(x.get("reviewed"))),
            x.get("accession", ""),
        )
    )

    selected = candidates[:top_n]

    for rank, item in enumerate(selected, 1):
        item["natural_rank"] = rank
        item["candidate_status"] = "SEARCHED_CANDIDATE"
        item["receptor_specificity_confirmed"] = False
        item["graftable_domain_confirmed"] = False
        item["ready_for_ring9"] = False

        if annotate_domains:
            try:
                de = extract_domain_evidence(item["accession"])
            except Exception as e:
                de = {
                    "accession": item.get("accession"),
                    "domain_boundary_confirmed": False,
                    "domains": [],
                    "crossrefs": [],
                    "receptor_binding_domain_confirmed": False,
                    "graftable_domain_confirmed": False,
                    "error": str(e),
                }
        else:
            de = None

        item["domain_evidence"] = de

        summary = summarize_rbp_evidence(
            item,
            receptor_evidence=item.get("receptor_evidence"),
            domain_evidence=de,
        )

        item["evidence_summary"] = summary
        item["protein_rbp_confirmed"] = summary.get(
            "protein_rbp_confirmed", False
        )
        item["domain_boundary_confirmed"] = summary.get(
            "domain_boundary_confirmed", False
        )
        item["receptor_binding_domain_confirmed"] = summary.get(
            "receptor_binding_domain_confirmed", False
        )
        item["graftable_domain_confirmed"] = summary.get(
            "graftable_domain_confirmed", False
        )
        item["ready_for_ring9"] = summary.get(
            "ready_for_ring9", False
        )

    return selected
