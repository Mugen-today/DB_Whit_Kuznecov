"""Build an installable QGIS ZIP without caches, datasets or environment files."""

from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]


def main():
    package = ROOT / "qgis_plugin"
    output = ROOT / "dist/qgis_mongodb.zip"
    output.parent.mkdir(exist_ok=True)
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for path in sorted(package.rglob("*")):
            if (
                path.is_file()
                and path.suffix in (".py", ".txt")
                and "__pycache__" not in path.parts
            ):
                archive.write(path, Path("qgis_plugin") / path.relative_to(package))
    print(output)


if __name__ == "__main__":
    main()
