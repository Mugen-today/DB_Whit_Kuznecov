"""Backend HTTP Dispatcher routing requests to backend/app/modules/."""

from datetime import datetime
import json
import urllib.parse
from wsgiref.simple_server import WSGIRequestHandler, make_server

from .database.mongodb import MongoDB
from .modules import analytics, export_data, import_data, query, spatial


class QuietHandler(WSGIRequestHandler):
    def log_message(self, *args):
        pass

    def setup(self):
        super().setup()
        self.connection.settimeout(90)


def _serialize(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    if hasattr(obj, "pattern"):
        return obj.pattern
    return str(obj)


def create_app(store):
    def application(environ, start_response):
        path = environ.get("PATH_INFO", "")
        method = environ.get("REQUEST_METHOD", "GET")
        query_str = environ.get("QUERY_STRING", "")
        content_type = environ.get("CONTENT_TYPE", "application/json")
        status = "200 OK"

        if path.startswith("/v1/qgis/"):
            from .modules import qgis_data

        if path == "/v1/qgis/points" or path.startswith("/v1/qgis/points/"):
            try:
                role, owner = qgis_data.identity(environ.get("HTTP_AUTHORIZATION", ""))
                identifier = path[len("/v1/qgis/points") :].strip("/")
                payload = {}
                if method in ("POST", "PUT"):
                    try:
                        length = int(environ.get("CONTENT_LENGTH") or 0)
                    except ValueError:
                        raise qgis_data.ApiError(400, "Invalid content length")
                    if not 0 < length <= 8192:
                        raise qgis_data.ApiError(
                            413, "Point payload must be 1..8192 bytes"
                        )
                    try:
                        payload = json.loads(environ["wsgi.input"].read(length))
                    except (ValueError, UnicodeError):
                        raise qgis_data.ApiError(400, "Invalid JSON")
                    if not isinstance(payload, dict):
                        raise qgis_data.ApiError(400, "JSON object required")
                body = qgis_data.execute(
                    store,
                    role,
                    owner,
                    method,
                    identifier,
                    urllib.parse.parse_qs(query_str),
                    payload,
                )
            except qgis_data.ApiError as exc:
                from http import HTTPStatus

                status = str(exc.status) + " " + HTTPStatus(exc.status).phrase
                body = {"detail": str(exc)}
            except Exception:
                status = "503 Service Unavailable"
                body = {
                    "detail": "Storage operation failed. Reload before retrying a write"
                }

        elif method == "POST" and path == "/v1/import-gpkg":
            try:
                length = int(environ.get("CONTENT_LENGTH") or 0)
                file_bytes = environ["wsgi.input"].read(length)
                fname = urllib.parse.unquote(
                    environ.get("HTTP_X_FILENAME", "dataset.gpkg")
                )
                body = import_data.execute(store, file_bytes=file_bytes, filename=fname)
            except Exception as exc:
                status = "500 Internal Server Error"
                body = {"detail": str(exc)}

        elif method == "POST" and path == "/v1/tz-query":
            try:
                length = int(environ.get("CONTENT_LENGTH") or 0)
                raw_body = environ["wsgi.input"].read(length).decode("utf-8")
                payload = json.loads(raw_body) if raw_body else {}
                q_type = payload.get("query_type", "q1_polygon")
                if q_type in ("q1_polygon", "q2_nearest", "q3_periods"):
                    body = spatial.execute(store, payload=payload)
                else:
                    body = analytics.execute(store, payload=payload)
            except Exception as exc:
                status = "500 Internal Server Error"
                body = {"detail": str(exc)}

        elif method == "POST" and path == "/v1/query":
            try:
                length = int(environ.get("CONTENT_LENGTH") or 0)
                raw_body = environ["wsgi.input"].read(length).decode("utf-8")
                body = query.execute(
                    store, raw_text=raw_body, content_type=content_type
                )
            except Exception as exc:
                status = "400 Bad Request"
                body = {"detail": str(exc)}

        elif method != "GET":
            status = "405 Method Not Allowed"
            body = {"detail": "Diagnostics accept GET only"}

        elif path == "/health/live":
            body = {"status": "alive", "scope": "storage-connector-only"}

        elif path == "/health/ready":
            try:
                store.ready()
                body = {"status": "ready", "checked": "five MongoDB service accounts"}
            except Exception:
                status = "503 Service Unavailable"
                body = {
                    "status": "not_ready",
                    "detail": "Storage connection or service authorization failed",
                }

        elif path == "/v1/statistics":
            try:
                from .modules import dashboard_stats
                body = dashboard_stats.execute(store)
            except Exception:
                status = "503 Service Unavailable"
                body = {"detail": "Statistics unavailable; check backend and Storage logs"}

        elif path in ("/v1/overview", "/v1/dashboard"):
            role = "reader"
            for part in query_str.split("&"):
                if part.startswith("role="):
                    role = part.split("=", 1)[1]
            try:
                body = export_data.execute(store, role=role)
            except Exception as exc:
                status = "500 Internal Server Error"
                body = {"detail": str(exc)}

        elif path == "/v1/geojson":
            role = "reader"
            for part in query_str.split("&"):
                if part.startswith("role="):
                    role = part.split("=", 1)[1]
            try:
                res = export_data.execute(store, role=role)
                features = [
                    {
                        "type": "Feature",
                        "geometry": {
                            "type": "Point",
                            "coordinates": [float(r["lon"]), float(r["lat"])],
                        },
                        "properties": r,
                    }
                    for r in res.get("records", [])
                    if r.get("lat") is not None and r.get("lon") is not None
                ]
                body = {
                    "type": "FeatureCollection",
                    "name": "SPb_LO_Foci_Schema",
                    "features": features,
                }
            except Exception as exc:
                status = "500 Internal Server Error"
                body = {"detail": str(exc)}

        elif path.startswith("/v1/"):
            status = "501 Not Implemented"
            body = {"detail": "Business API is not implemented in Storage phase"}

        else:
            status = "404 Not Found"
            body = {"detail": "Unknown endpoint"}

        data = json.dumps(body, default=_serialize).encode("utf-8")
        start_response(
            status,
            [
                ("Content-Type", "application/json"),
                ("Content-Length", str(len(data))),
                ("Cache-Control", "no-store"),
            ],
        )
        return [data]

    return application


def main():
    store = MongoDB()
    try:
        with make_server(
            "0.0.0.0", 8000, create_app(store), handler_class=QuietHandler
        ) as server:
            server.serve_forever()
    finally:
        store.close()


if __name__ == "__main__":
    main()
