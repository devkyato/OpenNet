# Changelog

All notable changes are documented here. OpenNet follows
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.1] - 2026-07-29

### Added

- Unified `opennet` CLI with `serve`, `send`, `ping`, and `benchmark` commands.
- Acknowledgement retries using stable IDs and the ONP/1 `DUPLICATE` flag.
- Bounded server duplicate suppression, connection limits, operational counters,
  receive queues, and connect timeouts.
- Mutual TLS options and secure-by-default remote CLI behavior.
- Generic Arduino `Stream` support for UART and Bluetooth Classic SPP transports.
- Typed Arduino receive accessors, readable error names, and ACK lookup helper.
- Hardened Linux/systemd installer bundle, checksums, and deterministic packages.
- Native C++ protocol tests, malformed-control tests, and retry/disconnect tests.
- Measured TCP/TLS/load benchmarks, protocol comparisons, tutorials, tips,
  transport boundaries, security guidance, and honest adoption analytics.

### Fixed

- Partial Arduino transport writes now complete the whole frame.
- Python receivers now wake with an error when a peer disconnects.
- Handler errors no longer expose exception details to remote peers.
- Control-frame validation is consistent across Python and Arduino.

## [0.1.0] - 2026-07-29

### Added

- ONP/1 protocol specification and typed binary framing.
- Python asyncio client and server.
- ESP32 Arduino client.
- Arduino IDE, PlatformIO, and Python examples.
- Cross-platform tests, CI, packaging, and contributor documentation.

[Unreleased]: https://github.com/devkyato/OpenNet/compare/v0.1.1...HEAD
[0.1.1]: https://github.com/devkyato/OpenNet/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/devkyato/OpenNet/releases/tag/v0.1.0
