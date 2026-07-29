"""Verify the repository-owned Arduino and Linux builders are deterministic."""

from __future__ import annotations

import hashlib
import sys
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_linux_bundle
import build_release


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(name: str, builder: Callable[[str | None], Path]) -> None:
    first_path = builder(None)
    first = digest(first_path)
    second_path = builder(None)
    second = digest(second_path)
    if first != second:
        raise SystemExit(f"{name} is not reproducible: {first} != {second}")
    print(f"{name}: {first}")


if __name__ == "__main__":
    verify("Arduino ZIP", build_release.build)
    verify("Linux bundle", build_linux_bundle.build)
