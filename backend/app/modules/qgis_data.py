"""Small authenticated point API for the Geodata collection."""

import hashlib
import hmac
import math
import os
import uuid
from bson import ObjectId
from bson.errors import InvalidId
from pymongo.errors import DuplicateKeyError


class ApiError(Exception):
    def __init__(self, status, message):
        self.status = status
        super().__init__(message)


def identity(header):
    token = header.removeprefix("Bearer ") if header.startswith("Bearer ") else ""
    for role, key in (("user", "QGIS_USER_TOKEN"), ("guest", "QGIS_GUEST_TOKEN"), ("reader", "DASHBOARD_TOKEN")):
        expected = os.environ.get(key, "")
        if (
            token
            and expected
            and hmac.compare_digest(token.encode("utf-8"), expected.encode("utf-8"))
        ):
            return role, "qgis-user" if role == "user" else "qgis-guest"
    raise ApiError(401, "A valid QGIS API token is required")


def feature(doc):
    lon, lat = doc.get("Longitude"), doc.get("Latitude")
    if not all(
        isinstance(x, (float, int)) and not isinstance(x, bool) and math.isfinite(x)
        for x in (lon, lat)
    ):
        return None
    if not -180 <= lon <= 180 or not -90 <= lat <= 90:
        return None
    return {
        "type": "Feature",
        "id": str(doc["_id"]),
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": {
            "mongo_id": str(doc["_id"]),
            "revision": doc.get("qgis_revision", 0),
            "elevation": doc.get("Elevation"),
        },
    }


def coordinates(payload):
    if set(payload) - {"longitude", "latitude", "elevation", "revision", "request_id"}:
        raise ApiError(400, "Unknown point fields")
    result = {}
    for key, field, low, high in (
        ("longitude", "Longitude", -180, 180),
        ("latitude", "Latitude", -90, 90),
    ):
        value = payload.get(key)
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or not low <= value <= high
        ):
            raise ApiError(400, "Coordinates must be finite WGS84 longitude/latitude")
        result[field] = float(value)
    height = payload.get("elevation")
    if height is not None:
        if (
            isinstance(height, bool)
            or not isinstance(height, (int, float))
            or not math.isfinite(height)
        ):
            raise ApiError(400, "Elevation must be finite or null")
        result["Elevation"] = float(height)
    return result


def execute(store, role, owner, method, identifier, params, payload):
    if method == "POST":
        raise ApiError(422, "All four groups are mandatory; use /v1/records")
    collection = store.database(role).Geodata
    scope = {"_owner_id": owner} if role == "user" else {}
    if method == "GET" and not identifier:
        try:
            limit = int(params.get("limit", ["200"])[0])
            after = params.get("after", [""])[0]
            if not 1 <= limit <= 500:
                raise ValueError()
            if after:
                scope["_id"] = {"$gt": ObjectId(after)}
        except (ValueError, TypeError, InvalidId):
            raise ApiError(400, "Invalid page parameters")
        docs = list(
            collection.find(scope, max_time_ms=1500).sort("_id", 1).limit(limit + 1)
        )
        visible = docs[:limit]
        features = [item for item in (feature(d) for d in visible) if item]
        return {
            "type": "FeatureCollection",
            "features": features,
            "role": role,
            "next": str(visible[-1]["_id"]) if len(docs) > limit else None,
            "skipped": len(visible) - len(features),
        }
    if role not in ("user","admin"):
        raise ApiError(403, "Guest access is read only")
    from .geometry import normalize
    data = normalize(coordinates(payload))
    data["_geometry_valid"]=True
    if method == "POST" and not identifier:
        try:
            request_id = str(uuid.UUID(payload["request_id"]))
        except (KeyError, ValueError, TypeError):
            raise ApiError(400, "request_id must be a UUID")
        doc_id = ObjectId(
            hashlib.sha256((owner + request_id).encode()).hexdigest()[:24]
        )
        doc = {"_id": doc_id, "_owner_id": owner, "qgis_revision": 1, **data}
        try:
            collection.insert_one(doc)
        except DuplicateKeyError:
            previous = collection.find_one({"_id": doc_id, "_owner_id": owner})
            if not previous or any(
                previous.get(k) != doc.get(k)
                for k in ("Longitude", "Latitude", "Elevation")
            ):
                raise ApiError(
                    409, "Request was already used with different coordinates"
                )
            return feature(previous)
        return feature(doc)
    if method == "PUT" and identifier:
        try:
            doc_id = ObjectId(identifier)
        except (ValueError, TypeError, InvalidId):
            raise ApiError(400, "Invalid document id")
        revision = payload.get("revision")
        if type(revision) is not int or revision < 0:
            raise ApiError(400, "A nonnegative revision is required")
        scope.update({"_id": doc_id})
        if revision == 0:
            scope["$or"] = [{"qgis_revision": 0}, {"qgis_revision": {"$exists": False}}]
        else:
            scope["qgis_revision"] = revision
        operation = {"$set": data, "$inc": {"qgis_revision": 1}}
        if "Elevation" not in data:
            operation["$unset"] = {"Elevation": ""}
        from pymongo import ReturnDocument

        updated = collection.find_one_and_update(
            scope, operation, return_document=ReturnDocument.AFTER
        )
        if not updated:
            raise ApiError(
                409,
                "Point changed, is unavailable or belongs to another user. Reload the layer",
            )
        return feature(updated)
    raise ApiError(405, "Unsupported point operation")
