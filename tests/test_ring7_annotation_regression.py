"""Ring7 annotation-quality regression cases.

This file records known annotation interpretation pitfalls.
It does not call external databases or execute the design pipeline.
"""

CASES = [
    {
        "protein": "CpsD",
        "accession": "P0C0T9",
        "issue": "cell surface describes capsular polysaccharide",
        "expected": "manual_review",
    },
    {
        "protein": "Sortase A",
        "accession": "Q8E5N2",
        "issue": "surface proteins describes substrates",
        "expected": "manual_review",
    },
    {
        "protein": "Enolase",
        "accession": "Q8RP81",
        "issue": "multiple localizations include cytoplasm and cell surface",
        "expected": "preserve_all_localization_evidence",
    },
]


def test_annotation_cases_have_provenance():
    for case in CASES:
        assert case["protein"]
        assert case["accession"]
        assert case["issue"]
        assert case["expected"]


if __name__ == "__main__":
    test_annotation_cases_have_provenance()
    print("ANNOTATION_REGRESSION_DATA_OK")
