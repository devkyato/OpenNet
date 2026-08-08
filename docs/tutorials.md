# Tutorials

## 1. Local Python round trip

Install the v0.2.2 wheel directly from the GitHub release:

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install \
  https://github.com/devkyato/OpenNet/releases/download/v0.2.2/opennet_protocol-0.2.2-py3-none-any.whl
```

Terminal one:

```sh
opennet serve --echo
```

Terminal two:

```sh
opennet ping --count 5
opennet send sensor/temperature 24.7 --type float
opennet send device/state '{"online":true,"battery":91}' --type json
```

## 2. Raspberry Pi service

Download and extract `OpenNet-linux-0.2.2.tar.gz`, then:

```sh
sudo ./install.sh
systemctl status opennet
journalctl -u opennet -f
```

It listens only on `127.0.0.1` by default. Use `--no-start` if you need to add
TLS before the first start. See [Security](security.md).

## 3. ESP32 over a trusted development LAN

1. Install `OpenNet-0.2.2.zip` through Arduino IDE's **Add .ZIP Library**.
2. Open **File > Examples > OpenNet > TelemetryClient**.
3. Enter the Wi-Fi details and the server's LAN address.
4. Start a development server with
   `opennet serve --host 0.0.0.0 --allow-plaintext`.
5. Upload and watch the serial monitor.

This plaintext mode is for a controlled lab. Use the
`SecureTelemetryClient` example and a CA certificate for shared networks.

## 4. ESP32 Bluetooth Classic SPP

Open `BluetoothSerialClient` on two original ESP32 boards (or pair one to a host
serial port). ONP framing runs over `BluetoothSerial`, so JSON, numbers, bytes,
ACKs, and CRC validation remain identical.

ESP32-C3 and ESP32-S3 do not support Bluetooth Classic SPP. BLE GATT requires a
future adapter and must not be described as supported by this release.

## 5. Measure your real network

Start the server and run:

```sh
opennet benchmark --host raspberrypi.local --ca lab-ca.crt \
  --count 1000 --warmup 25 --payload-size 64 --json
```

Repeat at different distances and busy periods. Record device versions, RSSI,
payload, sample count, reconnects, p50, p95, and maximum. A good report includes
failures and configuration, not only the best number.

## 6. Authorize a device topic

Once mutual TLS is working, the Python server can check the verified client
certificate and topic in an `authorizer`. I thought about putting this check in
each handler, but one callback is easier to audit and it runs before any handler
or ACK.

Start with the complete [certificate-to-topic example](authorization.md). Give
each device certificate a stable identity, map that identity to a narrow topic
prefix, and test both an allowed and denied topic before deployment.
