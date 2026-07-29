# Changelog

All notable changes are documented here. OpenNet follows
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.2.0] - 2026-07-29

### Added

- Optional synchronous or asynchronous server authorization before DATA handlers
  and acknowledgements.
- TLS state and verified peer-certificate access through the Python `Peer` API.
- Fail-closed authorization behavior, a denial counter, mutual-TLS integration
  coverage, and test-only certificate fixtures.
- A practical certificate-to-topic authorization guide and v0.2.0 release notes.

### Changed

- Release verification now includes the native Arduino tests and ESP32 build.
- Current install examples and package metadata target v0.2.0.

### Compatibility

- ONP/1 framing and typed-value encodings are unchanged.
- The Python server additions are optional and backward compatible.

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

[Unreleased]: https://github.com/devkyato/OpenNet/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/devkyato/OpenNet/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/devkyato/OpenNet/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/devkyato/OpenNet/releases/tag/v0.1.0
