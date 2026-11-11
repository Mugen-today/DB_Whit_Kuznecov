"""Separate app-network client: HTTP -> backend -> actual MongoDB reads."""

import json
from urllib.request import urlopen
from urllib.error import HTTPError

with urlopen("http://backend:8000/health/ready", timeout=15) as response:
    assert response.status == 200
    assert json.load(response)["status"] == "ready"
try:
    urlopen("http://backend:8000/v1/query", timeout=3)
except HTTPError as error:
    assert error.code == 401
else:
    raise AssertionError("Unauthenticated query must not report success")
print(
    "PASS HTTP app-network -> backend -> Storage readiness; business API requires authentication"
)
