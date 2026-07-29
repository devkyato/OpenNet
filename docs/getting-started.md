# Getting started

## Network model

One machine listens as the server; other devices connect as clients. On a home or
lab network, a Raspberry Pi is a convenient always-on server. OpenNet does not
bypass routers, firewalls, captive portals, or internet service outages.

I like starting on loopback first because it separates application mistakes from
Wi-Fi, certificates, and firewall rules. Once that works, move the exact same
ONP/1 messages onto the real transport.

## Raspberry Pi or backend server

OpenNet supports Python 3.9 or newer on operating systems supported by Python.
This includes current Raspberry Pi OS releases on Pi boards capable of running a
supported Python version.

```bash
python -m pip install \
  https://github.com/devkyato/OpenNet/releases/download/v0.2.0/opennet_protocol-0.2.0-py3-none-any.whl
opennet serve
```

On Windows, activate with `.venv\Scripts\activate`.

The default is loopback-only. Follow the [security guide](security.md) to configure
verified or mutual TLS before exposing the service.

## ESP32 with Arduino IDE

1. Download the release ZIP.
2. In Arduino IDE, choose **Sketch > Include Library > Add .ZIP Library**.
3. Install Espressif's `esp32` board package.
4. Open **File > Examples > OpenNet > TelemetryClient**.
5. Set Wi-Fi name, password, and the server's LAN IP address.
6. Select your exact ESP32 board and upload.

Call `client.poll()` frequently from `loop()`. OpenNet avoids blocking delays after
the TCP connection is established.

## PlatformIO and VS Code

Clone the repository and open the folder in VS Code with PlatformIO installed.
Build the included example:

```bash
pio run -e esp32dev
```

For another project:

```ini
lib_deps =
  https://github.com/devkyato/OpenNet.git#v0.2.0
```

## Sending values

Topics describe what a value means:

```cpp
client.sendText("lab/status", "online");
client.sendJson("lab/telemetry", "{\"temperature\":24.7}");
client.sendBinary("camera/chunk", bytes, byteCount);
client.sendInt("counter", 42);
client.sendDouble("voltage", 3.3);
client.sendBool("door/open", false);
```

Validate incoming JSON against an application schema and bound binary payload sizes
for the receiving device.

Continue with the [step-by-step tutorials](tutorials.md) and
[development tips](tips.md). When a server accepts more than one device, add
[topic authorization](authorization.md) instead of treating a valid certificate
as permission to use every topic.
