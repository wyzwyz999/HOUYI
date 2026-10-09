"""HOUYI Ring1 payload target selector.

Purpose
-------
Select function-disrupting payload targets from a broader bacterial
candidate target set.

Design principles
-----------------
1. Do not use wet-lab outcomes for discovery/ranking.
2. Keep scoring transparent and deterministic.
3. Count each biological concept at most once.
4. Avoid ambiguous substring matching where possible.
5. Do not require an experimental structure because Ring2 has fallback.
6. Extracellular recognition is primarily handled by Ring7/Ring8.
"""

import re


SELECTOR_VERSION = "payload_selector_v2"


# ----------------------------------------------------------------------
# Generic concept definitions
# ----------------------------------------------------------------------

POSITIVE_CONCEPTS = [
    (
        "essentiality",
        ["essential", "essential gene", "必需", "必需基因", "必需酶"],
        4.0,
    ),
    (
        "cell_division",
        ["cell division", "division protein", "细胞分裂"],
        3.0,
    ),
    (
        "peptidoglycan",
        ["peptidoglycan", "murein", "肽聚糖"],
        3.0,
    ),
    (
        "cell_wall_homeostasis",
        [
            "cell wall",
            "cell-wall",
            "cell envelope",
            "细胞壁",
            "细胞壁稳态",
        ],
        2.5,
    ),
    (
        "two_component_regulation",
        [
            "response regulator",
            "two-component system",
            "two component system",
            "sensor histidine kinase",
            "histidine kinase",
            "双组分系统",
            "反应调节蛋白",
        ],
        2.5,
    ),
    (
        "transcriptional_control",
        [
            "transcriptional regulator",
            "transcription regulator",
            "transcription factor",
            "转录调控",
            "转录调节",
        ],
        2.0,
    ),
    (
        "quorum_sensing",
        [
            "quorum sensing",
            "accessory gene regulator",
            "群体感应",
        ],
        1.5,
    ),
    (
        "antibiotic_resistance",
        [
            "antibiotic resistance",
            "methicillin resistance",
            "vancomycin resistance",
            "drug resistance",
            "耐药",
            "甲氧西林耐药",
        ],
        1.5,
    ),
]


DESIGN_CONCEPTS = [
    (
        "ppi_blockade",
        [
            "ppi inhibitor",
            "protein-protein interaction",
            "dimerization",
            "oligomerization",
            "二聚化",
            "多聚化",
            "蛋白互作",
        ],
        1.5,
    ),
    (
        "active_site_inhibition",
        [
            "active site",
            "catalytic site",
            "enzyme inhibition",
            "活性位点",
            "催化位点",
            "酶活性位点",
        ],
        1.5,
    ),
    (
        "functional_blockade",
        [
            "inhibitor",
            "inhibition",
            "blockade",
            "block ",
            "阻断",
            "抑制",
        ],
        1.0,
    ),
]


# Strong evidence that a target is primarily extracellular/secreted
# and therefore unsuitable as the default intracellular payload target.
HARD_EXCLUDE_CONCEPTS = [
    (
        "secreted_toxin",
        [
            "hemolysin",
            "leukocidin",
            "alpha-toxin",
            "alpha toxin",
            "pore-forming toxin",
            "exotoxin",
            "enterotoxin",
            "成孔毒素",
            "杀白细胞素",
        ],
    ),
    (
        "surface_adhesin",
        [
            "mscramm",
            "adhesin",
            "clumping factor",
            "fibronectin-binding protein",
            "collagen-binding protein",
            "粘附素",
        ],
    ),
]


NEGATIVE_CONCEPTS = [
    (
        "surface_protein",
        [
            "surface protein",
            "surface antigen",
            "cell surface protein",
            "表面蛋白",
            "表面抗原",
        ],
        -3.0,
    ),
    (
        "biofilm_surface_role",
        [
            "biofilm",
            "生物膜",
        ],
        -1.5,
    ),
    (
        "nutrient_surface_receptor",
        [
            "siderophore receptor",
            "heme receptor",
            "hemoglobin receptor",
            "transferrin receptor",
            "铁摄取受体",
        ],
        -2.5,
    ),
]


# ----------------------------------------------------------------------
# Text utilities
# ----------------------------------------------------------------------

def _normalize(value):
    if value is None:
        return ""
    return " ".join(str(value).strip().lower().split())


def _candidate_text(meta):
    """Build discovery text WITHOUT wetlab_status."""
    rationale = meta.get("rationale") or {}

    fields = [
        meta.get("gene"),
        meta.get("protein"),
        meta.get("mechanism_class"),
        meta.get("function"),
        meta.get("design_strategy"),
        rationale.get("virulence_relevance"),
        rationale.get("conservation"),
        rationale.get("host_homology"),
    ]

    return _normalize(
        " ".join(str(x) for x in fields if x)
    )


def _is_ascii_term(term):
    return all(ord(c) < 128 for c in term)


def _contains_term(text, term):
    """Safer phrase matching.

    English/ASCII phrases use token-like boundaries to reduce accidental
    substring matches. Chinese phrases use exact substring matching.
    """
    text = _normalize(text)
    term = _normalize(term)

    if not text or not term:
        return False

    if not _is_ascii_term(term):
        return term in text

    # Allow flexible whitespace inside multiword English phrases.
    escaped = re.escape(term)
    escaped = escaped.replace(r"\ ", r"\s+")

    pattern = rf"(?<![a-z0-9]){escaped}(?![a-z0-9])"
    return re.search(pattern, text, flags=re.IGNORECASE) is not None


def _first_match(text, terms):
    for term in terms:
        if _contains_term(text, term):
            return term
    return None


# ----------------------------------------------------------------------
# Scoring
# ----------------------------------------------------------------------

def score_payload_target(target_id, meta):
    """Return one fully auditable payload-suitability record."""

    text = _candidate_text(meta)

    score = 0.0
    reasons = []
    excluded = False
    matched_concepts = []

    # 1. Hard exclusions
    for concept, terms in HARD_EXCLUDE_CONCEPTS:
        matched = _first_match(text, terms)
        if matched:
            excluded = True
            matched_concepts.append(concept)
            reasons.append(
                f"EXCLUDE:{concept}({matched})"
            )

    # 2. Positive biology concepts: each concept can score only once.
    for concept, terms, weight in POSITIVE_CONCEPTS:
        matched = _first_match(text, terms)
        if matched:
            score += weight
            matched_concepts.append(concept)
            reasons.append(
                f"+{weight}:{concept}({matched})"
            )

    # 3. Designability concepts: each concept only once.
    for concept, terms, weight in DESIGN_CONCEPTS:
        matched = _first_match(text, terms)
        if matched:
            score += weight
            matched_concepts.append(concept)
            reasons.append(
                f"+{weight}:{concept}({matched})"
            )

    # 4. Negative suitability concepts.
    for concept, terms, weight in NEGATIVE_CONCEPTS:
        matched = _first_match(text, terms)
        if matched:
            score += weight
            matched_concepts.append(concept)
            reasons.append(
                f"{weight}:{concept}({matched})"
            )

    # 5. Structure availability is only a mild bonus.
    # No structure is NOT a failure because Ring2 can predict it.
    if meta.get("pdb"):
        score += 0.5
        reasons.append("+0.5:experimental_or_reference_structure")

    # 6. Very coarse compute/designability prior.
    length = meta.get("length_aa")
    if not isinstance(length, (int, float)):
        seq = meta.get("sequence") or ""
        if seq:
            length = len(seq)

    if isinstance(length, (int, float)):
        if length > 1200:
            score -= 2.0
            reasons.append("-2.0:very_long_target")
        elif 80 <= length <= 700:
            score += 0.5
            reasons.append("+0.5:practical_target_length")

    return {
        "selector_version": SELECTOR_VERSION,
        "target_id": target_id,
        "score": round(float(score), 3),
        "excluded": bool(excluded),
        "matched_concepts": list(dict.fromkeys(matched_concepts)),
        "reasons": reasons,
    }


def rank_payload_targets(targets_meta):
    """Return deterministic full ranking."""

    ranked = [
        score_payload_target(tid, meta)
        for tid, meta in targets_meta.items()
    ]

    # Eligible first, then score descending, then target ID ascending.
    ranked.sort(
        key=lambda x: (
            x["excluded"],
            -x["score"],
            x["target_id"],
        )
    )

    return ranked


def select_payload_targets(targets_meta, top_n=1):
    """Return selected target IDs plus complete ranking audit."""

    try:
        top_n = int(top_n)
    except (TypeError, ValueError):
        top_n = 1

    top_n = max(1, top_n)

    ranked = rank_payload_targets(targets_meta)

    eligible = [
        x for x in ranked
        if not x["excluded"]
    ]

    selected = [
        x["target_id"]
        for x in eligible[:top_n]
    ]

    return selected, ranked
