# Architecture

OpenNet separates the parts that must interoperate from platform-specific I/O.

```text
Application values and topics
           |
      OpenNet API
           |
   ONP/1 frame codec       <- language-neutral and tested with vectors
           |
 TCP or TLS byte stream    <- reliable ordered transport
           |
 Wi-Fi / Ethernet / OS networking
```

The Python package provides the reference codec plus asyncio client and server. The
Arduino library uses the ESP32 networking clients and a bounded receive state
machine. Both implementations use the same 24-byte header.

## Reliability

TCP already retransmits lost packets and preserves order. ONP/1 acknowledgements
add application-level evidence that a complete frame was parsed and accepted.
Applications needing durable delivery must persist outgoing messages and decide
how to handle duplicates after reconnecting; OpenNet does not pretend RAM queues
survive power loss.

## Latency

OpenNet disables Nagle's algorithm where supported, uses a compact header, and
does not require a broker round trip. Actual latency still depends on radio
conditions, access-point load, power-saving mode, operating-system scheduling, and
the application. Low-signal or disconnected areas cannot be made reliable by a
software library alone.

## Planned extensions

- Authenticated session handshake and topic authorization helpers.
- Optional service discovery for trusted LANs.
- Persistent outbound queues.
- TypeScript and portable C bindings.

Extensions will be proposed in issues and specified before implementation.
