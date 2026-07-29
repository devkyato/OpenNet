# Embedded memory model

Memory on the embedded side deserves a concrete explanation because “small API”
does not automatically mean “small object.” OpenNet uses bounded frame content,
but it also uses Arduino `String`, `std::vector`, and `std::function`; their
object sizes, capacity growth, allocator metadata, and fragmentation behavior
depend on the board core and toolchain.

I do not publish one universal `sizeof(OpenNetClient)` number for that reason. A
native desktop value would not describe an ESP32 build, and even an ESP32 value
would omit the Wi-Fi, Bluetooth, or TLS stack surrounding it.

## Fixed-width protocol fields

The Arduino API declares these representations explicitly:

| Field | Representation |
|---|---:|
| Receive header buffer | 24 bytes |
| `OpenNetFrameKind` | 1 byte |
| `OpenNetValueType` | 1 byte |
| `OpenNetError` | 1 byte |
| Message ID | 4 bytes |
| Flags | 1 byte |
| INT64/FLOAT64 temporary send buffer | 8 bytes |

Compile-time assertions protect the three one-byte enums. C++ may still insert
padding inside structs, so the table must not be added together and presented as
the total object size.

## Receive allocation

The client validates the 24-byte header before allocating a frame body. The body
contains:

```text
topic bytes + payload bytes
```

The topic is bounded to 1,024 bytes. Payload bytes are bounded by the
constructor's `maxPayload`, which defaults to 4,096 bytes. At the default, the
largest accepted body therefore contains 5,120 bytes. Vector capacity and
allocator bookkeeping may be larger than the logical content.

In the default API, after CRC and type validation OpenNet moves that same body
allocation into the `OpenNetMessage` payload used by the callback. It shifts
payload bytes over the topic prefix but does not allocate and copy a second
payload vector. After the callback, the client takes the vector back so its
capacity can be reused by the next frame.

The topic is still copied into an Arduino `String` for the callback. Calling
`OpenNetMessage::text()` creates another `String` containing a UTF-8 or JSON
payload. The typed scalar accessors read the eight-byte or one-byte payload
without creating a text copy.

## Caller-owned receive mode

For long-running firmware that must avoid receive-path heap allocation, pass a
caller-owned body buffer and register the function-pointer view callback:

```cpp
uint8_t receiveBody[576];
WiFiClient transport;
OpenNetClient client(transport, receiveBody, sizeof(receiveBody), 512);

void onView(const OpenNetMessageView& message, void*) {
  // topic and payload are byte spans, not null-terminated strings.
  // They remain valid only for this callback.
}

void setup() {
  client.onMessageView(onView);
}
```

This path stores the frame body in `receiveBody` and calls a plain function
pointer with topic/payload spans. It does not construct an Arduino `String`,
payload vector, or capturing `std::function` for delivery. The 576-byte example
is only an application choice: it can hold a 64-byte topic plus a 512-byte
payload, not the protocol's maximum 1,024-byte topic.

If the declared topic plus payload exceeds the supplied capacity, the client
sets `ReceiveBufferTooSmall` and closes the `Client` transport. Registering the
legacy `onMessage` callback as well still creates its convenient `String` and
vector copies.

## Send allocation

Sending does not assemble a complete frame in one heap buffer. The client writes
a 24-byte stack header, the caller's topic bytes, and the caller's payload bytes
in sequence. Partial transport writes are completed before moving to the next
part. Typed integers and doubles use an eight-byte stack buffer.

## Choosing a payload limit

Set `maxPayload` to the largest payload the device must actually receive, plus no
speculative margin. For example:

```cpp
WiFiClient transport;
OpenNetClient client(transport, 512);
```

That changes the accepted payload bound to 512 bytes; the protocol topic bound
remains 1,024 bytes. Short application topics reduce real allocations even
though the protocol permits longer ones.

Also account separately for:

- Wi-Fi, TCP, TLS, Bluetooth, or serial buffers;
- application objects retained by the callback;
- JSON parsing performed by the application;
- task stacks and other firmware components;
- allocator fragmentation over the intended run time.

OpenNet cannot guarantee that allocations elsewhere in the Arduino core,
transport, TLS stack, or application are absent or recoverable. The caller-owned
mode only removes OpenNet's dynamic allocation from the receive-body and callback
delivery path.

## Control-loop and ACK bounds

`poll()` processes at most 256 transport bytes per call by default. Pass a
smaller or larger byte budget explicitly when the surrounding control loop has a
different latency target. Outbound writes cooperatively yield between partial
writes and fail after the configured total write deadline; OpenNet cannot
preempt a transport whose individual `write()` call blocks internally.

The Arduino client permits at most eight ACK-required sends to remain pending.
`TooManyPendingAcks` rejects the next one until an ACK arrives. The most recent
eight acknowledged IDs are retained for `acknowledged(id)`; this is bounded
process memory, not durable delivery state.

## Measuring a real firmware

PlatformIO's build summary reports static RAM and flash for the whole firmware,
not OpenNet alone. Use it as a reproducible whole-image baseline, then measure
free heap and largest free block on the exact board, core, transport, TLS mode,
payload mix, and run duration. Report those conditions with the numbers; do not
generalize one sketch's result to every ESP32 target.
