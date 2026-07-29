# Development tips

- Start on loopback (`127.0.0.1`) and run `opennet ping` before adding a radio.
- Use short, stable topics such as `lab1/sensor3/temperature`; put changing data
  in the value, not the topic.
- Set the smallest realistic `max_payload`. An ESP32 should not inherit a backend
  server's multi-megabyte allowance.
- Remember that an Arduino receive buffer can hold `maxPayload + 1024` bytes of
  frame body. See the [embedded memory model](embedded-memory.md) before choosing
  a limit.
- Call Arduino `poll()` every loop iteration. Long `delay()` calls postpone ACKs,
  pings, and incoming messages.
- Retry idempotent operations. For actions such as “unlock door,” include an
  application operation ID and persist processed IDs.
- Use JSON for evolving records, typed numbers for frequent scalar telemetry, and
  bytes for already encoded data.
- Prefer `asInt`, `asDouble`, and `asBool` when possible. Calling `text()` creates
  a new Arduino `String` containing the payload.
- Do not base64-encode binary data; ONP carries bytes directly.
- Use `opennet benchmark` on the deployment network and report p95/p99, not only
  the fastest observation.
- Treat an ACK as peer acceptance, not durable storage or physical action.
- Validate JSON shape, topic authorization, ranges, and binary format in the
  application handler.
- Never publish private keys, Wi-Fi passwords, addresses, or production
  certificates in an issue or example.
