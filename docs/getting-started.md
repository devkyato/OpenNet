# Getting started

## Network model

One machine listens as the server; other devices connect as clients. On a home or
lab network, a Raspberry Pi is a convenient always-on server. OpenNet does not
bypass routers, firewalls, captive portals, or internet service outages.

## Raspberry Pi or backend server

OpenNet supports Python 3.9 or newer on operating systems supported by Python.
This includes current Raspberry Pi OS releases on Pi boards capable of running a
supported Python version.

```bash
git clone https://github.com/devkyato/OpenNet.git
cd OpenNet
python -m venv .venv
source .venv/bin/activate
python -m pip install -e "./python"
opennet-server --host 0.0.0.0 --port 8765
```

On Windows, activate with `.venv\Scripts\activate`.

The example server logs metadata, not full binary payloads. For internet-facing
deployments, configure TLS and an application authorization policy before opening
the firewall.

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
  https://github.com/devkyato/OpenNet.git#v0.1.0
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
