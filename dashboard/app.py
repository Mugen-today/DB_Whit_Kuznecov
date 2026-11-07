"""Planned service; intentionally no fake successful HTTP dashboard."""

import os

BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8000")
if __name__ == "__main__":
    raise SystemExit(
        "Dashboard not implemented. Storage scope only; BACKEND_URL contract reserved."
    )
