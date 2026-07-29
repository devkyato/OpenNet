# Compatibility

## Supported

| Platform | Minimum | Status | Verification |
|---|---|---|---|
| Python | CPython 3.9 | Supported | CI on 3.9–3.13 |
| Raspberry Pi OS | Python 3.9+ | Supported | Same pure-Python code; hardware reports invited |
| ESP32 Arduino core | 2.x, 3.x | Supported | CI compile for `esp32dev`; hardware reports invited |
| VS Code | Current + PlatformIO | Supported workflow | PlatformIO configuration |
| Arduino IDE | 2.x | Supported workflow | `library.properties` and examples |

## Not claimed

- Original ESP8266, RP2040/Pico W, Arduino UNO WiFi, or non-ESP32 Arduino boards.
- Every historical Raspberry Pi OS image. A board must run a maintained Python
  3.9+ environment and have working TCP/IP networking.
- Guaranteed operation through NAT, captive portals, or without network coverage.
- Real-time deadlines or safety certification.

## Adding a report

Open a compatibility issue with:

- exact device and revision;
- OS, Python, Arduino core, and toolchain versions;
- Wi-Fi or Ethernet adapter;
- client/server example used;
- duration, message count, payload sizes, and observed failures.

Verified reports may be promoted into the supported table.
