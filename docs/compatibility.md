# Compatibility

## Supported

| Platform | Minimum | Status | Verification |
|---|---|---|---|
| Python | CPython 3.9 | Supported | CI on 3.9–3.14 |
| Raspberry Pi OS | Python 3.9+ | Supported | Pure Python and Linux bundle; hardware reports invited |
| ESP32 Arduino | Current PlatformIO package | Supported alpha | `esp32dev` compile and native protocol tests |
| VS Code | Current + PlatformIO | Supported workflow | Checked-in PlatformIO configuration |
| Arduino IDE | 2.x | Supported workflow | Library metadata and examples |

“Raspberry Pi support” means any model and operating-system image able to run a
supported CPython version and provide the chosen connection. It does not imply
that every historical Pi image, radio, or adapter has been physically tested.

## Not claimed

- ESP8266, RP2040/Pico W, Arduino UNO WiFi, or non-ESP32 Arduino boards.
- Every historical Raspberry Pi OS image.
- Direct BLE GATT support. Bluetooth Classic SPP works only on ESP32 targets that
  provide it; ESP32-C3/S3 do not.
- Guaranteed operation through NAT, captive portals, firewalls, or without
  network coverage.
- Real-time deadlines, independent security audit, or safety certification.

## Adding a field report

Open a compatibility issue with:

- exact device, revision, OS, Python/Arduino core, and toolchain;
- Wi-Fi/Ethernet/Bluetooth adapter and access point;
- connection type and TLS mode;
- example or application commit used;
- duration, message count, payload sizes, and reconnect/failure count;
- RSSI/range and p50/p95/p99 latency when applicable.

Verified reports may be promoted into the supported table. A failed test is useful
evidence too; do not omit it.
