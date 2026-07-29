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
- Project positioning now emphasizes direct embedded-to-host communication, and
  the reliable-stream boundary explicitly documents why raw UDP is unsupported.
- Arduino receive handling now moves the validated body buffer into the callback
  message instead of allocating and copying a second payload vector.
- ACK semantics now explicitly mean validated transport acceptance before
  handler completion; delivery guarantees and timeout/overload policies are
  documented without changing ONP/1 bytes.

### Fixed

- Python PING no longer cycles forever when DATA arrives before PONG.
- A full Python application queue no longer blocks ACK and control processing;
  overflow now sends ERROR and closes explicitly.
- Python message-ID wrap skips IDs with pending ACK futures.
- Python JSON decoding rejects non-standard `NaN` and infinity constants.
- Python client writes now have a configurable timeout.
- Python servers ACK accepted DATA before bounded handler dispatch, so slow
  handlers no longer block PING or turn completed side effects into ACK timeout
  ambiguity.
- Python servers bound idle/header/body/TLS/write/handler waits and reject a full
  handler set explicitly.
- Python and Arduino now share malformed UTF-8/JSON conformance vectors, enforce
  strict text/control encoding, and bound JSON nesting to 32.
- Arduino polling has a configurable byte budget, partial writes have a deadline
  and cooperative yield, generic sends enforce typed invariants, and ACK tracking
  uses bounded pending/history tables.
- Arduino applications can provide a fixed receive buffer and function-pointer
  message view to avoid OpenNet receive-path heap allocation.
- The CLI rejects oversized files before reading them, logs payload metadata
  rather than values by default, offers a shared topic-prefix allowlist, and
  labels its benchmark as sequential acknowledged round trips.
- A Python server at its connection limit now sends a best-effort ERROR before
  closing the rejected connection.
- GitHub Actions dependencies are pinned to immutable upstream commits with
  readable release-version comments.
- Deterministic fault tests cover concurrent sends, every truncation point of a
  valid frame, fragmented ACK delivery, and a reproducible 24-byte-header
  mutation corpus.

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
