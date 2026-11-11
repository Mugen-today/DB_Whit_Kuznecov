"""Read the single schema source locally or from its container mount."""

import json
import os
from pathlib import Path


def load_schema():
    default = Path(__file__).resolve().parents[3] / "storage/schema/model.json"
    path = Path(os.environ.get("STORAGE_SCHEMA_PATH", default))
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)
