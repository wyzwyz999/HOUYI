import requests

URL = "https://rest.uniprot.org/uniprotkb/search"

def check_response(response):
    if response.status_code == 429:
        return "RATE_LIMITED"
    if response.status_code >= 500:
        return "SERVER_ERROR"
    if response.status_code != 200:
        return "HTTP_ERROR"

    try:
        data = response.json()
    except ValueError:
        return "INVALID_JSON"

    if not isinstance(data, dict):
        return "INVALID_FORMAT"
    if not isinstance(data.get("results"), list):
        return "INVALID_FORMAT"

    return "SUCCESS"


class FakeResponse:
    def __init__(self, status, data=None):
        self.status_code = status
        self.data = data

    def json(self):
        return self.data


assert check_response(FakeResponse(200, {"results": []})) == "SUCCESS"
assert check_response(FakeResponse(429)) == "RATE_LIMITED"
assert check_response(FakeResponse(503)) == "SERVER_ERROR"
assert check_response(FakeResponse(404)) == "HTTP_ERROR"
assert check_response(FakeResponse(200, {})) == "INVALID_FORMAT"

print("HTTP_CLASSIFICATION_TEST_PASS")
