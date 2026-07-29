# OpenNet Protocol 1 (ONP/1)

Status: stable for the OpenNet 0.x series.

ONP/1 is a framed, topic-based messaging protocol. It is intentionally smaller
than a broker protocol: peers establish a reliable byte stream (normally TCP or
TLS), exchange frames, and decide at the application layer which topics are
allowed.

A transport must preserve every byte in order for the lifetime of the
connection. Datagram loss, reordering, fragmentation, and session semantics are
outside ONP/1. An adapter for a datagram transport must satisfy the stream
contract before passing bytes to this protocol.

## Byte order and limits

All multibyte integers and floating-point values use network byte order (big
endian). A receiver must reject frames with a payload length greater than
16,777,216 bytes before allocating the payload. Embedded applications should set a
smaller limit.

## Frame

The fixed header is 24 bytes:

| Offset | Size | Field | Meaning |
|---:|---:|---|---|
| 0 | 2 | magic | ASCII `ON` (`0x4f 0x4e`) |
| 2 | 1 | version | `0x01` |
| 3 | 1 | kind | frame kind |
| 4 | 1 | flags | bit field |
| 5 | 1 | value type | application payload type |
| 6 | 2 | topic length | UTF-8 topic byte length |
| 8 | 4 | message ID | unsigned, non-zero for DATA |
| 12 | 4 | payload length | application payload bytes |
| 16 | 4 | CRC-32 | CRC of topic bytes followed by payload bytes |
| 20 | 4 | reserved | must be zero; ignore when receiving |

The header is followed by `topic length` bytes and then `payload length` bytes.
Topics must be valid UTF-8, between 1 and 1024 bytes for DATA frames, and use `/`
as an optional hierarchy separator.

## Frame kinds

| Value | Name | Topic/payload |
|---:|---|---|
| 1 | DATA | typed application message |
| 2 | ACK | empty; message ID identifies accepted DATA |
| 3 | PING | empty |
| 4 | PONG | empty |
| 5 | CLOSE | optional UTF-8 reason |
| 6 | ERROR | UTF-8 diagnostic; must not contain secrets |

Unknown frame kinds must produce ERROR and close the connection. A peer receiving
PING should promptly return PONG.

## Flags

- Bit 0 (`0x01`), `ACK_REQUIRED`: receiver sends ACK after accepting a DATA frame.
- Bit 1 (`0x02`), `DUPLICATE`: retransmission of the same message ID.
- Bits 2–7 are reserved and must be zero when sending.

ACK confirms that the receiver parsed and accepted the frame, not that application
side effects completed. Message IDs are scoped to one connection. Receivers should
deduplicate repeated IDs for the duration of the connection.

## Value types

| Value | Type | Encoding |
|---:|---|---|
| 0 | BYTES | uninterpreted bytes |
| 1 | UTF8 | valid UTF-8 |
| 2 | JSON | UTF-8 JSON value |
| 3 | INT64 | signed 64-bit integer |
| 4 | FLOAT64 | IEEE-754 binary64 |
| 5 | BOOL | exactly one byte: `0x00` or `0x01` |
| 6 | NULL | empty payload |

Kind-specific control payloads use the encoding described in the frame-kind table,
regardless of the value-type byte.

## CRC

CRC-32 is the IEEE polynomial used by zlib. Initialize to zero through the public
zlib-style API and calculate over the exact topic bytes, then continue over the
payload bytes. The expected value for topic `sensor/temp` and payload `24.5` is
defined by the conformance tests.

CRC protects against accidental corruption only. TLS is required for
confidentiality, peer authentication, and tamper resistance.

## Connection lifecycle

1. Connect a reliable byte stream.
2. Either peer may send DATA or PING.
3. Send PING after an application-configured idle interval; require PONG before
   the liveness timeout.
4. Send CLOSE when practical before ending a healthy connection.
5. Reconnect with exponential backoff and jitter. Application code decides whether
   to replay unacknowledged messages.

## Compatibility

Senders must use version 1. A version-1 receiver must ignore non-zero reserved
header bytes for forward compatibility but reject reserved flag bits. New value
types or frame kinds require a protocol revision or an extension specification.

OpenNet v0.2.0 adds an optional Python server authorization callback without
changing the ONP/1 frame, kinds, flags, types, or connection lifecycle. A denied
DATA frame receives the existing ERROR control frame and the connection closes;
it is not acknowledged.
