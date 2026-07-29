"""Build the self-contained Linux/systemd release bundle."""

from __future__ import annotations

import argparse
import gzip
import io
import re
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXED_MTIME = 1_700_000_000


def _version() -> str:
    text = (ROOT / "python" / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version = "([^"]+)"$', text, re.MULTILINE)
    if not match:
        raise SystemExit("could not read package version")
    return match.group(1)


def _add_bytes(archive: tarfile.TarFile, name: str, data: bytes, mode: int) -> None:
    info = tarfile.TarInfo(name)
    info.size = len(data)
    info.mode = mode
    info.mtime = FIXED_MTIME
    info.uid = 0
    info.gid = 0
    info.uname = "root"
    info.gname = "root"
    archive.addfile(info, io.BytesIO(data))


def build(expected_version: str | None = None) -> Path:
    version = _version()
    if expected_version is not None and expected_version != version:
        raise SystemExit(
            f"requested version {expected_version} does not match project {version}"
        )
    wheels = sorted((ROOT / "python" / "dist").glob(f"opennet_protocol-{version}-*.whl"))
    if len(wheels) != 1:
        raise SystemExit("build the Python wheel before the Linux bundle")

    output = ROOT / "dist" / f"OpenNet-linux-{version}.tar.gz"
    output.parent.mkdir(exist_ok=True)
    prefix = f"OpenNet-linux-{version}"
    with (
        output.open("wb") as raw,
        gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=FIXED_MTIME) as compressed,
        tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as archive,
    ):
        for name in (
            "install.sh",
            "uninstall.sh",
            "opennet.service",
            "opennet.env",
            "README.md",
        ):
            source = ROOT / "packaging" / "linux" / name
            mode = 0o755 if name.endswith(".sh") else 0o644
            _add_bytes(archive, f"{prefix}/{name}", source.read_bytes(), mode)
        _add_bytes(
            archive,
            f"{prefix}/{wheels[0].name}",
            wheels[0].read_bytes(),
            0o644,
        )
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-version")
    print(build(parser.parse_args().expected_version))
