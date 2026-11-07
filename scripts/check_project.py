"""Portable source/distribution checks. No Docker and no project dependencies."""

import ast
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    for path in ROOT.rglob("*.py"):
        if ".venv" not in path.parts and "venv" not in path.parts:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    schemas = list((ROOT / "storage/schema").glob("*.json"))
    if schemas != [ROOT / "storage/schema/model.json"]:
        raise RuntimeError("Expected one canonical model.json")
    for path in ROOT.rglob("*.json"):
        if ".venv" not in path.parts and "venv" not in path.parts:
            json.loads(path.read_text(encoding="utf-8"))
    if not shutil.which("node"):
        raise RuntimeError("Node.js is required for JavaScript syntax checks")
    for extension in ("*.js", "*.cjs"):
        for path in ROOT.rglob(extension):
            subprocess.run(["node", "--check", str(path)], check=True)
    for relative in (
        "tests/__init__.py",
        "tests/unit/__init__.py",
        "README.md",
        "docs/STUDENT_GUIDE.md",
        ".gitignore",
        ".gitattributes",
    ):
        if not (ROOT / relative).is_file():
            raise RuntimeError("Missing distribution file: " + relative)
    print("PASS source syntax, JSON and required distribution files")


if __name__ == "__main__":
    main()
