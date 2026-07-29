"""Build and validate the Arduino release ZIP with only installable files."""

from __future__ import annotations

import argparse
import json
import re
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEXT_FILES = [
    "README.md",
    "LICENSE",
    "CHANGELOG.md",
    "library.properties",
    "library.json",
    "keywords.txt",
]
DIRECTORIES = ["src", "examples", "docs"]


def versions() -> dict[str, str]:
    properties = (ROOT / "library.properties").read_text(encoding="utf-8")
    arduino = re.search(r"^version=(.+)$", properties, re.MULTILINE)
    metadata = json.loads((ROOT / "library.json").read_text(encoding="utf-8"))
    pyproject = (ROOT / "python" / "pyproject.toml").read_text(encoding="utf-8")
    python = re.search(r'^version = "([^"]+)"$', pyproject, re.MULTILINE)
    init = (ROOT / "python" / "src" / "opennet" / "__init__.py").read_text(
        encoding="utf-8"
    )
    package = re.search(r'^__version__ = "([^"]+)"$', init, re.MULTILINE)
    if not arduino or not python or not package:
        raise SystemExit("Could not read every project version")
    return {
        "arduino": arduino.group(1),
        "platformio": str(metadata["version"]),
        "python": python.group(1),
        "package": package.group(1),
    }


def build(expected: str | None) -> Path:
    project_versions = versions()
    unique = set(project_versions.values())
    if len(unique) != 1:
        raise SystemExit(f"Version mismatch: {project_versions}")
    version = unique.pop()
    if expected is not None and expected != version:
        raise SystemExit(f"Tag version {expected} does not match project {version}")

    output = ROOT / "dist" / f"OpenNet-{version}.zip"
    output.parent.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as temporary:
        staging = Path(temporary) / "OpenNet"
        staging.mkdir()
        for relative in TEXT_FILES:
            target = staging / relative
            target.write_bytes((ROOT / relative).read_bytes())
        for directory in DIRECTORIES:
            for source in (ROOT / directory).rglob("*"):
                if source.is_file():
                    target = staging / source.relative_to(ROOT)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(source.read_bytes())
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            for source in sorted(staging.rglob("*")):
                if source.is_file():
                    archive.write(source, source.relative_to(staging.parent))
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-version")
    result = build(parser.parse_args().expected_version)
    print(result)
