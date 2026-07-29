# Why ONP/1 exists

There are already many good communication protocols. OpenNet does not exist
because MQTT, HTTP, WebSocket, or raw TCP are missing. It exists because I wanted
one small protocol whose complete communication contract could be read, tested,
and discussed across an embedded device and a Python host.

The concrete use case is intentionally specialized: an ESP32 sends typed sensor
data, status, or commands directly to a Raspberry Pi or backend service, and the
same frame can also travel over another reliable Arduino stream. A project that
needs a broker, browser interoperability, retained state, discovery, or fleet
management should normally choose an established protocol that already owns
those responsibilities.

## The gap ONP/1 explores

Raw TCP gives an application an ordered byte stream, but it does not define
message boundaries, types, topics, limits, corruption checks, or application
acknowledgements. A small project has to invent those rules somewhere.

ONP/1 makes those rules explicit:

- one fixed 24-byte header;
- seven value types with exact encodings;
- UTF-8 topics and bounded lengths;
- CRC-32 for accidental corruption;
- optional ACKs with stable IDs for retries;
- strict malformed-frame behavior;
- identical test vectors in Python and Arduino.

This is not the smallest possible byte count. It is a trade: some framing
overhead buys a contract that can be inspected and implemented consistently.

## Why not just use MQTT?

MQTT is usually the better answer for brokered publish/subscribe, retained
messages, fleet fan-out, offline sessions, and established operational tooling.
OpenNet deliberately has no broker and no subscription protocol. Its direct
client/server topology is simpler only when the application actually wants a
direct connection.

## Why not HTTP or WebSocket?

HTTP is the natural fit for web APIs, proxies, caches, and request/response
integrations. WebSocket is the natural fit for browser-compatible full-duplex
communication. OpenNet has no browser-native API and does not inherit those
ecosystems.

## Why not stay with raw TCP?

Raw TCP is appropriate when an application genuinely needs its own framing and
is prepared to specify and test it. ONP/1 is the reusable result of making those
decisions once for a narrow ESP32/Python use case.

## Learning value

I think this is where the project can help most honestly: it facilitates focused
learning about communication design. The code keeps byte order, framing,
partial reads and writes, validation, ACK meaning, retry identity, duplicate
suppression, resource bounds, and TLS responsibilities visible.

That educational value does not prove adoption, hardware reach, performance, or
security. Those claims still require evidence. It only means the repository is
small enough to trace a value from an Arduino call, through ONP/1 bytes, into a
Python handler—and then question every design choice along the way.

## Deliberate non-goals

- General cross-platform RPC or service discovery.
- Brokered pub/sub, retained messages, or offline fleet queues.
- Browser-native communication.
- Making unreliable datagrams behave like streams.
- Hiding application authorization or durable-operation design.
- Replacing a protocol that already fits a deployment.

See the [protocol comparison](comparison.md) for a capability table, the
[transport contract](transports.md) for the byte-stream boundary, and the
[architecture](architecture.md) for how the pieces fit together.
