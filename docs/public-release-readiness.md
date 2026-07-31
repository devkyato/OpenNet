# OpenNet public release readiness

This document defines the work required to make OpenNet easy to discover, install, evaluate, and use without overstating its maturity.

## Positioning

OpenNet should be presented as a small, inspectable typed messaging protocol for direct ESP32-to-Python links over reliable ordered streams. It should not be marketed as a replacement for MQTT, HTTP, WebSocket, or a durable event system.

## Release blockers

- Complete and publish the reproducible 24-hour ESP32 to Raspberry Pi interoperability report.
- Add a process-wide handler semaphore and authorization semaphore.
- Add a dedicated authorization timeout and isolate blocking synchronous authorizers.
- Provide application-level operation IDs and result receipts in one end-to-end example.
- Publish a threat model that distinguishes TLS peer authentication, topic authorization, CRC corruption detection, ACK acceptance, and durable application completion.

## Usability improvements

- Add `opennet init` to generate a minimal server/client project with secure defaults.
- Add `opennet doctor` to check Python version, certificates, bind address, port availability, payload limits, and connectivity.
- Add `opennet examples` and `opennet schema` commands so examples and protocol limits are discoverable from the CLI.
- Add structured JSON output for `ping`, `send`, `benchmark`, and `doctor`.
- Add reconnect-policy presets for interactive, telemetry, and command use cases.
- Add an application receipt example for database writes and device commands.

## Documentation site

Publish a versioned documentation site with:

1. five-minute local quickstart;
2. ESP32 Wi-Fi quickstart;
3. Raspberry Pi systemd deployment;
4. TLS and mutual-TLS setup;
5. authorization recipes;
6. delivery-semantics guide;
7. troubleshooting and error catalogue;
8. protocol reference and test vectors;
9. measured compatibility reports;
10. migration notes by release.

Every page should include a maturity banner: alpha, tested platforms, untested platforms, and known limitations.

## Discoverability

Expand package and repository search terms to include `embedded messaging`, `iot protocol`, `arduino`, `micropython`, `device telemetry`, `raspberry pi server`, `binary framing`, `tcp protocol`, and `tls messaging` where accurate. Add repository topics, Open Graph artwork, a concise social preview, FAQ headings matching common search queries, and links between the GitHub repository, documentation site, package index, and release page.

## Publication targets

- PyPI for `opennet-protocol` after trusted publishing is configured.
- GitHub Releases for wheel, sdist, Arduino ZIP, Linux bundle, checksums, and SBOM.
- Arduino Library Manager only after metadata, examples, semantic versioning, and physical-hardware evidence are complete.
- Read the Docs or GitHub Pages for versioned documentation.

## Release automation

Use an environment-protected trusted-publishing workflow. A tag release must verify tests, native Arduino tests, ESP32 builds, reproducibility, package installation, documentation links, checksums, SBOM generation, and artifact signatures before publication.

## Success criteria

A new user should be able to find OpenNet through a relevant search, understand when not to use it, install it in one command, run a secure local example in five minutes, diagnose common failures, and verify published artifacts.