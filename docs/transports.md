# Transports

ONP/1 needs a reliable, ordered sequence of bytes. It does not require a specific
radio.

That sentence is the transport contract, not just a recommendation. ONP/1 frames
may arrive in many partial reads, but their bytes must arrive once and in order.
TCP, TLS, UART with an appropriate link, USB serial, and Bluetooth Classic SPP
can provide that shape. The quality of reconnects, buffering, and the physical
link still belongs to the chosen transport.

| Connection | v0.2.0 path | Security | Notes |
|---|---|---|---|
| Wi-Fi/Ethernet/LAN | TCP | TLS recommended | Python and ESP32 |
| Internet/VPN | TCP | Verified TLS required by CLI | Routers/firewalls still apply |
| ESP32 Wi-Fi | `WiFiClient` / `WiFiClientSecure` | Prefer `WiFiClientSecure` | All targets need a compatible ESP32 Arduino core |
| UART/USB serial | Arduino `Stream` | Physical/access controls | Already-open stream |
| Bluetooth Classic SPP | ESP32 `BluetoothSerial` stream | Pairing plus app controls | Original ESP32; not C3/S3 |
| BLE GATT | Not direct in v0.2.0 | Pairing is not app authorization | Needs fragmentation/reassembly adapter |

An internet connection does not make arbitrary devices discoverable or reachable.
Peers still need an address, route, open firewall, and listening service. Offline
radio links work only while both devices are in range.

## What a stream adapter must provide

An adapter is responsible for:

- preserving byte order;
- not silently dropping bytes inside a connection;
- exposing partial reads until one complete ONP/1 frame can be assembled;
- completing or clearly failing partial writes;
- defining when a connection or stream session has ended.

ONP ACKs sit above that contract. They confirm that a complete DATA frame was
parsed and accepted; they do not repair missing bytes in the middle of a stream.
Reconnect policy and replay of unacknowledged application messages remain
application decisions.

## UDP and other datagram transports

Raw UDP is not an ONP/1 transport. Datagrams may be lost, duplicated, reordered,
or truncated, and their boundaries are different from a continuous byte stream.
Passing a UDP socket directly to the current codec would violate its assumptions.

A future datagram adapter would need its own documented layer for packet
fragmentation, reassembly, ordering, loss detection, retransmission, duplicate
handling, size limits, and session identity. That layer could carry unchanged
ONP/1 frame bytes after reassembly, but its behavior would need separate tests
and an extension specification before the repository claimed support.

Applications can also build that adapter themselves. In that case, OpenNet
begins only after the adapter exposes a reliable ordered stream; the adapter's
reliability and performance are not OpenNet guarantees.

## Arduino stream use

```cpp
#include <BluetoothSerial.h>
#include <OpenNet.h>

BluetoothSerial radio;
OpenNetClient openNet(radio);

void setup() {
  radio.begin("OpenNet-ESP32");
}

void loop() {
  openNet.poll();
  // Once the SPP peer is connected:
  // openNet.sendText("device/status", "online");
}
```

The same constructor works with `Serial2` after the application calls
`Serial2.begin(...)`. For network clients, keep using `OpenNetClient(WiFiClient&)`
and `connect(host, port)`.
