"""Disposable-container smoke check for the QGIS backend contract."""

import json
import os
import uuid
from urllib.request import Request, urlopen
from urllib.error import HTTPError

BASE = os.environ.get("QGIS_TEST_BACKEND", "http://backend:8000")


def request(method, path, payload=None, guest=False, expected=200):
    key = "QGIS_GUEST_TOKEN" if guest else "QGIS_USER_TOKEN"
    req = Request(
        BASE + path,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={
            "Authorization": "Bearer " + os.environ[key],
            "Content-Type": "application/json",
        },
        method=method,
    )
    try:
        response = urlopen(req, timeout=15)
    except HTTPError as error:
        response = error
    with response:
        body = json.load(response)
        assert response.status == expected, (response.status, body)
        return body


payload = {"longitude": 30.31, "latitude": 59.95, "request_id": str(uuid.uuid4())}
first = request("POST", "/v1/qgis/points", payload)
assert request("POST", "/v1/qgis/points", payload)["id"] == first["id"]
path = "/v1/qgis/points/" + first["id"]
changed = {"longitude": 30.4, "latitude": 60.0, "revision": 1}
assert request("PUT", path, changed)["properties"]["revision"] == 2
request("PUT", path, changed, expected=409)
request("PUT", path, {**changed, "revision": 2}, guest=True, expected=403)
page = request("GET", "/v1/qgis/points")
assert any(
    f["id"] == first["id"] and f["geometry"]["coordinates"] == [30.4, 60.0]
    for f in page["features"]
)
print(
    "PASS QGIS backend HTTP write/read, duplicate retry, optimistic conflict and guest denial"
)
