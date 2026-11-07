"""Storage connection diagnostic only. Full backend API is intentionally not implemented."""

import json
from wsgiref.simple_server import make_server, WSGIRequestHandler
from .database.mongodb import MongoDB


class QuietHandler(WSGIRequestHandler):
    def log_message(self, *args):
        pass

    def setup(self):
        super().setup()
        self.connection.settimeout(15)


def create_app(store):
    def application(environ, start_response):
        path = environ.get("PATH_INFO", "")
        status = "200 OK"
        if environ.get("REQUEST_METHOD") != "GET":
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
        elif path.startswith("/v1/"):
            status = "501 Not Implemented"
            body = {"detail": "Business API is not implemented in Storage phase"}
        else:
            status = "404 Not Found"
            body = {"detail": "Unknown endpoint"}
        data = json.dumps(body).encode()
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
