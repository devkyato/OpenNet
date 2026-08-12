# Release process

I keep releases intentionally mechanical. The interesting decisions belong in
the code and changelog; the tag should only package a commit that has already
passed every check.

1. Confirm CI passes on `main`.
2. Update `CHANGELOG.md` and versions in `library.properties`, `library.json`, and
   `python/pyproject.toml`.
3. Create and push an annotated `vX.Y.Z` tag.
4. The release workflow verifies that all versions match, runs Python and native
   Arduino tests, compiles the ESP32 example, builds the Python wheel/source
   distribution, Arduino ZIP, Linux/systemd bundle, and SHA-256 checksums, then
   creates a GitHub release.
5. A maintainer checks installation from the published artifacts and edits the
   generated release notes if needed.

PyPI publication is intentionally not automatic until the owner configures trusted
publishing. Release assets remain installable and reproducible without a registry
credential.

## v0.2.3 assets

| Asset | Use |
|---|---|
| `OpenNet-0.2.3.zip` | Arduino IDE library |
| `opennet_protocol-0.2.3-py3-none-any.whl` | Direct pip/pipx install |
| `opennet_protocol-0.2.3.tar.gz` | Python source distribution |
| `OpenNet-linux-0.2.3.tar.gz` | `sudo` Linux/systemd install |
| `SHA256SUMS` | Artifact integrity verification |
