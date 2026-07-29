"""Write SHA-256 checksums for every distributable release asset."""

from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    assets = sorted(
        [
            *ROOT.joinpath("dist").glob("OpenNet-*"),
            *ROOT.joinpath("python", "dist").glob("*"),
        ],
        key=lambda path: path.name.lower(),
    )
    assets = [path for path in assets if path.is_file() and path.name != "SHA256SUMS"]
    if not assets:
        raise SystemExit("no release assets found")
    lines = [f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}" for path in assets]
    (ROOT / "dist" / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
