"""通用分页结果质量检查，不执行靶向设计。"""

def validate_pages(pages, expected_total):
    if not isinstance(expected_total, int) or expected_total < 0:
        raise ValueError("INVALID_TOTAL")

    if not isinstance(pages, list):
        raise ValueError("INVALID_PAGES")

    records = []
    for page in pages:
        if not isinstance(page, list):
            raise ValueError("INVALID_PAGE")
        records.extend(page)

    if any(not isinstance(r, dict) or not r.get("id") for r in records):
        raise ValueError("INVALID_RECORD")

    ids = [str(r["id"]) for r in records]
    unique_count = len(set(ids))

    if unique_count != len(ids):
        status = "DUPLICATE_RECORDS"
    elif unique_count < expected_total:
        status = "INCOMPLETE_DATA"
    elif unique_count > expected_total:
        status = "COUNT_MISMATCH"
    else:
        status = "COMPLETE"

    return {
        "status": status,
        "expected_total": expected_total,
        "retrieved_count": len(records),
        "unique_count": unique_count,
        "page_count": len(pages),
    }
