# OpenNet

![OpenNet cover](docs/assets/opennet-cover.png)

[![CI](https://github.com/devkyato/OpenNet/actions/workflows/ci.yml/badge.svg)](https://github.com/devkyato/OpenNet/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-4a638f.svg)](LICENSE)
[![Protocol](https://img.shields.io/badge/protocol-ONP%2F1-4a638f.svg)](docs/protocol.md)

OpenNet is a small, typed messaging protocol and library for sending JSON, text,
numbers, and arbitrary binary data between ESP32 devices, Raspberry Pi computers,
and backend services over Wi-Fi or Ethernet.

The first release deliberately targets one dependable path: an ESP32 client and a
Python 3.9+ client/server communicating over TCP. The wire format is documented and
language-neutral, so additional transports and language bindings can be added
without inventing incompatible message formats.

## What it provides

- A compact binary frame with versioning, message IDs, type information, CRC-32,
  and a 16 MiB defensive payload limit.
- JSON, UTF-8 text, signed integers, IEEE-754 doubles, booleans, null, and raw bytes.
- Async Python client/server APIs for Raspberry Pi and backend systems.
- An Arduino-compatible ESP32 client with reconnect, heartbeat, and delivery ACKs.
- Optional TLS at the transport layer.
- Arduino IDE, PlatformIO, Python, and VS Code examples.
- Protocol conformance tests and cross-platform CI.

## Five-minute start

Run the Python server:

```bash
python -m pip install -e "./python[dev]"
opennet-server --host 0.0.0.0 --port 8765
```

Install this repository as an Arduino library, open
`File > Examples > OpenNet > TelemetryClient`, set the Wi-Fi credentials and
server address, then upload it to an ESP32.

Python clients are equally small:

```python
import asyncio
from opennet import OpenNetClient

async def main():
    async with OpenNetClient("192.168.1.50", 8765) as client:
        await client.send("temperature", {"celsius": 24.7})

asyncio.run(main())
```

See the [getting-started guide](docs/getting-started.md), [protocol
specification](docs/protocol.md), and [compatibility policy](docs/compatibility.md).

## Project status

OpenNet is pre-1.0 software. ONP/1 framing is stable for the v0.x series, while
higher-level APIs may improve based on real hardware feedback. Do not represent
untested boards or operating systems as supported; add a compatibility report when
you test one.

## Contributing

Student contributions are welcome. Good first tasks are labeled in the issue
tracker, and every feature should include tests or a reproducible hardware test
report. Read [CONTRIBUTING.md](CONTRIBUTING.md) and the
[code of conduct](CODE_OF_CONDUCT.md) before opening a pull request.

## Security

CRC detects accidental corruption; it is not encryption or authentication. Use TLS
on untrusted networks. See [SECURITY.md](SECURITY.md) for the threat model and
private reporting instructions.

## License

OpenNet is available under the [MIT License](LICENSE).
