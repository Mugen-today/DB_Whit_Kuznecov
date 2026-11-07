"""Future HTTP client configuration; never store MongoDB credentials in QGIS."""

BACKEND_URL = "http://127.0.0.1:8000"


def query(*args, **kwargs):
    raise NotImplementedError("The backend query API is not implemented")
