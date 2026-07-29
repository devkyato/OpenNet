# Transports

ONP/1 needs a reliable, ordered sequence of bytes. It does not require a specific
radio.

| Connection | v0.1.1 path | Security | Notes |
|---|---|---|---|
| Wi-Fi/Ethernet/LAN | TCP | TLS recommended | Python and ESP32 |
| Internet/VPN | TCP | Verified TLS required by CLI | Routers/firewalls still apply |
| ESP32 Wi-Fi | `WiFiClient` / `WiFiClientSecure` | Prefer `WiFiClientSecure` | All targets need a compatible ESP32 Arduino core |
| UART/USB serial | Arduino `Stream` | Physical/access controls | Already-open stream |
| Bluetooth Classic SPP | ESP32 `BluetoothSerial` stream | Pairing plus app controls | Original ESP32; not C3/S3 |
| BLE GATT | Not direct in v0.1.1 | Pairing is not app authorization | Needs fragmentation/reassembly adapter |

An internet connection does not make arbitrary devices discoverable or reachable.
Peers still need an address, route, open firewall, and listening service. Offline
radio links work only while both devices are in range.

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
