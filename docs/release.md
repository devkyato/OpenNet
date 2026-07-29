# Release process

1. Confirm CI passes on `main`.
2. Update `CHANGELOG.md` and versions in `library.properties`, `library.json`, and
   `python/pyproject.toml`.
3. Create and push an annotated `vX.Y.Z` tag.
4. The release workflow verifies that all versions match, runs tests, builds the
   Python wheel/source distribution and Arduino ZIP, then creates a GitHub release.
5. A maintainer checks installation from the published artifacts and edits the
   generated release notes if needed.

PyPI publication is intentionally not automatic until the owner configures trusted
publishing. Release assets remain installable and reproducible without a registry
credential.
