"""UniProt HTTP 响应检查。"""

def check_response(status_code, data):
    if status_code == 429:
        return "RATE_LIMITED"
    if status_code >= 500:
        return "SERVER_ERROR"
    if status_code != 200:
        return "HTTP_ERROR"
    if not isinstance(data, dict):
        return "INVALID_FORMAT"
    if not isinstance(data.get("results"), list):
        return "INVALID_FORMAT"
    return "SUCCESS"


def check_coverage(total, retrieved):
    if total is None:
        return "TOTAL_UNKNOWN"
    if retrieved > total:
        return "COUNT_MISMATCH"
    if retrieved < total:
        return "INCOMPLETE"
    return "COMPLETE"


if __name__ == "__main__":
    assert check_response(200, {"results": []}) == "SUCCESS"
    assert check_response(429, None) == "RATE_LIMITED"
    assert check_response(503, None) == "SERVER_ERROR"
    assert check_response(200, {}) == "INVALID_FORMAT"
    assert check_coverage(1151, 500) == "INCOMPLETE"
    assert check_coverage(1151, 1151) == "COMPLETE"
    print("UNIPROT_DATA_LAYER_TEST_PASS")
