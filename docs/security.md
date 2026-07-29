# Security guide

OpenNet is secure only when its deployment matches its threat model. CRC-32 is an
integrity check for accidental corruption; it does not stop an attacker.

## Recommended modes

| Environment | Minimum mode |
|---|---|
| One-process tests | Plain loopback |
| Trusted, isolated classroom LAN | TLS preferred; plaintext only by explicit choice |
| Shared Wi-Fi, campus, or internet | Verified TLS |
| Devices that must be individually trusted | Mutual TLS plus topic authorization |
| Safety-critical control | Not supported without an independent safety design |

The CLI refuses non-loopback plaintext unless `--allow-plaintext` is supplied.
The server defaults to `127.0.0.1`. `--insecure` still encrypts but disables
certificate verification and is for diagnosis only.

## Verified TLS

Server:

```sh
opennet serve --host 0.0.0.0 \
  --tls-cert server.crt --tls-key server.key
```

Client:

```sh
opennet send sensor/temperature 24.7 --type float \
  --host opennet.example.net --ca lab-ca.crt
```

For mutual TLS, add `--tls-client-ca devices-ca.crt` to the server and
`--cert device.crt --key device.key` to the client. Issue a distinct certificate
per device so one device can be revoked without replacing every key.

## Application responsibilities

- Authorize which device may publish or receive each topic.
- Validate decoded values, JSON schemas, ranges, and file formats.
- Keep private keys outside the repository and restrict filesystem permissions.
- Rotate certificates and define a revocation process.
- Persist operation IDs when duplicate physical actions would be dangerous.
- Rate-limit expensive handlers and monitor `ServerStats`.
- Keep payload and connection limits appropriate for available RAM and CPU.

## Current limits

ONP/1 has no message-level signature or session authorization handshake.
TLS protects network streams, but a peer with an accepted certificate can still
send any topic unless the application checks it. Bluetooth pairing is not a
replacement for application authorization. OpenNet has not been independently
audited or certified.
