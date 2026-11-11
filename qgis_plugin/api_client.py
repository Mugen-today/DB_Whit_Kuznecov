"""Asynchronous requests using QGIS networking and its proxy settings."""

import json
from urllib.parse import urlsplit,quote
from qgis.PyQt.QtCore import QByteArray, QTimer, QUrl
from qgis.PyQt.QtNetwork import QNetworkRequest
from qgis.core import QgsNetworkAccessManager


class GisApiClient:
    def __init__(self, backend_url, token, username=""):
        parts = urlsplit(backend_url)
        if (
            parts.scheme not in ("http", "https")
            or not parts.hostname
            or parts.username
            or parts.password
            or parts.query
            or parts.fragment
        ):
            raise ValueError(
                "Enter an HTTP(S) backend URL without credentials or query"
            )
        if parts.scheme == "http" and parts.hostname not in (
            "localhost",
            "127.0.0.1",
            "::1",
        ):
            raise ValueError("Use HTTPS for a remote backend")
        if not token.strip() or any(c in token for c in "\r\n"):
            raise ValueError("Enter the API token from the backend configuration")
        self.backend_url = backend_url.rstrip("/")
        self.token = token.strip()
        self.pending = set()
        self.username=username

    def request(self, method, path, payload, success, failure):
        request = QNetworkRequest(QUrl(self.backend_url + path))
        if self.username:request.setRawHeader(b"X-GIS-User",quote(self.username,safe="").encode("ascii"))
        request.setRawHeader(b"Authorization", ("Bearer " + self.token).encode("ascii"))
        request.setRawHeader(b"Content-Type", b"application/octet-stream" if isinstance(payload,bytes) else b"application/json")
        request.setAttribute(
            QNetworkRequest.RedirectPolicyAttribute,
            QNetworkRequest.ManualRedirectPolicy,
        )
        manager = QgsNetworkAccessManager.instance()
        data = (
            QByteArray(payload if isinstance(payload,bytes) else json.dumps(payload).encode("utf-8"))
            if payload is not None
            else QByteArray()
        )
        reply = manager.sendCustomRequest(request, method.encode("ascii"), data)
        self.pending.add(reply)
        timer = QTimer(reply)
        timer.setSingleShot(True)
        timer.timeout.connect(reply.abort)
        timer.start(180000 if path.startswith("/v1/console") else 60000)

        def finished():
            timer.stop()
            self.pending.discard(reply)
            try:
                raw = bytes(reply.readAll())
                if len(raw) > 128 * 1024 * 1024:
                    raise ValueError("Response exceeds 128 MB")
                status = reply.attribute(QNetworkRequest.HttpStatusCodeAttribute)
                body = json.loads(raw) if raw else {}
                if status is None or not 200 <= int(status) < 300:
                    raise ValueError(
                        body.get(
                            "detail", "Backend connection failed or request timed out"
                        )
                    )
                success(body)
            except Exception as error:
                failure(str(error))
            finally:
                reply.deleteLater()

        reply.finished.connect(finished)

    def close(self):
        for reply in tuple(self.pending):
            reply.abort()
