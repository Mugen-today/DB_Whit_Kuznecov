"""Backend HTTP Dispatcher routing requests to backend/app/modules/."""

from datetime import datetime
import json
import urllib.parse
from wsgiref.simple_server import WSGIRequestHandler, WSGIServer, make_server
from socketserver import ThreadingMixIn
from threading import BoundedSemaphore

class BoundedServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True
    slots = BoundedSemaphore(8)
    def process_request(self, request, address):
        self.slots.acquire()
        try:
            super().process_request(request, address)
        except BaseException:
            self.slots.release()
            raise
    def process_request_thread(self, request, address):
        try:
            super().process_request_thread(request, address)
        finally:
            self.slots.release()

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

        if path.startswith("/v1/"):
            from .modules import records, qgis_data
            try:
                from .auth.principals import identity
                role, owner = identity(environ.get("HTTP_AUTHORIZATION", ""),environ.get("HTTP_X_GIS_USER",""))
                length = int(environ.get("CONTENT_LENGTH") or 0)
                binary_chunk=path.startswith("/v1/gpkg/uploads/") and path.endswith("/chunk")
                maximum=4*1024*1024 if binary_chunk else 32*1024*1024 if path=="/v1/gpkg/upload" else 2*1024*1024
                if length < 0 or length > maximum:
                    raise qgis_data.ApiError(413, "Payload exceeds allowed bytes: "+str(maximum))
                params = urllib.parse.parse_qs(query_str)
                payload = {}
                if path == "/v1/import-gpkg":
                    raise qgis_data.ApiError(422, "Legacy import disabled: all four record groups are mandatory; use /v1/records")
                if method in ("POST", "PUT", "PATCH") and path!="/v1/gpkg/upload" and not binary_chunk:
                    if length == 0:
                        raise qgis_data.ApiError(400, "JSON body required")
                    try:
                        raw=environ["wsgi.input"].read(length)
                        if path=="/v1/query":
                            from .modules import query_api
                            payload=query_api.parse(raw.decode("utf-8"),content_type)
                        else:
                            payload = json.loads(raw,
                                parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
                    except (ValueError, UnicodeError):
                        raise qgis_data.ApiError(400, "Invalid JSON")
                    if not isinstance(payload, dict):
                        raise qgis_data.ApiError(400, "JSON object required")
                if path=="/v1/session" and method=="GET":
                    body={**records.catalog(role),"role":role,"owner":owner,"can_write":role in ("user","admin"),"backend_version":"0.8.0"}
                elif path=="/v1/gpkg/uploads" and method=="POST":
                    from .modules import gpkg_uploads,entities
                    entities.write_role(role);body=gpkg_uploads.begin(payload,owner)
                elif path.startswith("/v1/gpkg/uploads/"):
                    from .modules import gpkg_uploads,entities
                    entities.write_role(role);parts=path.split('/');identifier=parts[4]
                    if len(parts)==5 and method=="GET":body=gpkg_uploads.status(identifier,owner)
                    elif len(parts)==6 and parts[5]=='chunk' and method=="PUT":
                        try:offset=int(params.get('offset',[''])[0])
                        except ValueError:raise qgis_data.ApiError(400,'Chunk offset required')
                        data=environ['wsgi.input'].read(length)
                        if len(data)!=length:raise qgis_data.ApiError(400,'Incomplete upload chunk')
                        body=gpkg_uploads.chunk(identifier,owner,offset,data)
                    elif len(parts)==6 and parts[5]=='complete' and method=="POST":body=gpkg_uploads.finish(identifier,owner)
                    else:raise qgis_data.ApiError(404,'Unknown upload operation')
                elif path=="/v1/gpkg/jobs" and method=="POST":
                    from .modules import gpkg_jobs
                    body=gpkg_jobs.start(store,role,owner,payload)
                elif path.startswith("/v1/gpkg/jobs/"):
                    from .modules import gpkg_jobs
                    parts=path.split('/');identifier=parts[4]
                    if len(parts)==5 and method=="GET":body=gpkg_jobs.status(role,owner,identifier)
                    elif len(parts)==6 and parts[5]=='validate' and method=="POST":body=gpkg_jobs.validate(store,role,owner,identifier)
                    elif len(parts)==6 and parts[5]=='apply' and method=="POST":body=gpkg_jobs.apply(store,role,owner,identifier)
                    else:raise qgis_data.ApiError(404,'Unknown import job operation')
                elif path=="/v1/gpkg/upload" and method=="POST":
                    from .modules import gpkg_import
                    if role not in ("user","admin"):raise qgis_data.ApiError(403,"User token required")
                    body=gpkg_import.upload(environ["wsgi.input"].read(length),owner)
                elif path in ("/v1/gpkg/validate","/v1/gpkg/apply") and method=="POST":
                    from .modules import gpkg_import
                    body=gpkg_import.execute(store,role,owner,payload,apply=path.endswith("/apply"))
                elif path == "/v1/console" and method == "POST":
                    from .modules import mongo_console
                    body=mongo_console.execute(store,role,owner,payload)
                elif path == "/v1/collections" and method == "GET":
                    body = records.catalog(role)
                elif path.startswith("/v1/collections/"):
                    parts = path.split("/")[3:]
                    if len(parts) == 1 and method == "GET":
                        body = records.page(store, role, owner, parts[0], params)
                    elif len(parts)==2 and parts[1]=="batch" and method=="POST":
                        from .modules import entities
                        body=entities.edit_batch(store,role,owner,parts[0],payload)
                    elif len(parts) == 2 and method == "PATCH":
                        from .modules import entities
                        body=entities.edit(store,role,owner,parts[0],parts[1],payload)
                    else:
                        raise qgis_data.ApiError(405, "Use POST /v1/records for complete new records")
                elif path == "/v1/records" and method == "POST":
                    body = records.create(store, role, owner, payload)
                elif path == "/v1/import-gpkg":
                    raise qgis_data.ApiError(422, "Legacy import disabled: all four record groups are mandatory; use /v1/records")
                elif path == "/v1/query" and method == "POST":
                    from .modules import query_api
                    body=query_api.execute(store,role,owner,payload)
                elif path == "/v1/qgis/points" or path.startswith("/v1/qgis/points/"):
                    if method == "POST":
                        raise qgis_data.ApiError(422, "A point alone is insufficient: use /v1/records with all four groups")
                    body = qgis_data.execute(store, role, owner, method,
                        path[len("/v1/qgis/points"):].strip("/"), params, payload)
                elif path == "/v1/statistics" and method == "GET":
                    from .modules import dashboard_stats
                    body = dashboard_stats.execute(store,role,owner)
                elif path in ("/v1/overview", "/v1/dashboard", "/v1/geojson") and method == "GET":
                    selected = "guest" if role == "guest" or params.get("role")==["guest"] else role
                    body = export_data.execute(store, role=selected, owner=owner,params=params)
                    if path == "/v1/geojson":
                        body = {"type":"FeatureCollection","features":[
                            {"type":"Feature","geometry":{"type":"Point","coordinates":[d["lon"],d["lat"]]},"properties":d}
                            for d in body["records"] if d["lon"] is not None and d["lat"] is not None]}
                elif path == "/v1/tz-query" and method == "POST":
                    if role != "reader":
                        raise qgis_data.ApiError(403, "Dashboard service access required")
                    payload["role"] = "guest" if payload.get("role")=="guest" else "reader"
                    module = spatial if payload.get("query_type") in ("q1_polygon","q2_nearest","q3_periods") else analytics
                    body = module.execute(store, payload=payload)
                else:
                    raise qgis_data.ApiError(404, "Unknown endpoint")
            except qgis_data.ApiError as exc:
                from http import HTTPStatus
                status = str(exc.status) + " " + HTTPStatus(exc.status).phrase
                body = {"detail":str(exc)}
            except (ValueError, TypeError):
                status = "400 Bad Request"
                body = {"detail":"Invalid request"}
            except Exception as exc:
                import logging
                logging.error("Backend request failed: %s", type(exc).__name__)
                status = "503 Service Unavailable"
                body = {"detail":"Storage operation failed; retry with the same request_id"}

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

        else:
            status = "404 Not Found"
            body = {"detail": "Unknown endpoint"}

        data = json.dumps(body, default=_serialize, ensure_ascii=False).encode("utf-8")
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
            "0.0.0.0", 8000, create_app(store), handler_class=QuietHandler, server_class=BoundedServer
        ) as server:
            server.serve_forever()
    finally:
        store.close()


if __name__ == "__main__":
    main()
