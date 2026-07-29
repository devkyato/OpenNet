"""Check that local Markdown links resolve inside the repository."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
LINK = re.compile(r"!?\[[^\]]*]\(([^)]+)\)")


def main() -> None:
    failures: list[str] = []
    for document in sorted(ROOT.rglob("*.md")):
        if any(part.startswith(".") for part in document.relative_to(ROOT).parts):
            continue
        text = document.read_text(encoding="utf-8")
        for raw_target in LINK.findall(text):
            target = raw_target.strip().split(maxsplit=1)[0].strip("<>")
            if (
                not target
                or target.startswith(("#", "http://", "https://", "mailto:"))
            ):
                continue
            path_text = unquote(target.split("#", 1)[0])
            destination = (document.parent / path_text).resolve()
            if ROOT not in destination.parents and destination != ROOT:
                failures.append(f"{document.relative_to(ROOT)}: escapes repository: {target}")
            elif not destination.exists():
                failures.append(f"{document.relative_to(ROOT)}: missing: {target}")
    if failures:
        raise SystemExit("\n".join(failures))
    print("All local Markdown links resolve.")


if __name__ == "__main__":
    main()
