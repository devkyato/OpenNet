# Command-line reference

`opennet --help` exposes four commands.

## Serve

```sh
opennet serve [--host HOST] [--port PORT] [--echo]
```

Useful controls include `--max-payload`, `--max-connections`,
`--deduplication-window`, `--tls-cert`, `--tls-key`, and `--tls-client-ca`.
Remote plaintext listeners require `--allow-plaintext`.

The general-purpose CLI server logs or echoes messages; it does not accept a
custom topic policy on the command line. Use the Python `OpenNetServer`
`authorizer` API when certificate-to-topic rules are required.

## Send

```sh
opennet send TOPIC [VALUE] [--type TYPE]
```

Types are `text`, `json`, `int`, `float`, `bool`, `null`, `hex`, and `file`.
The command waits for an ACK by default and retries twice. Adjust with
`--retries`, `--retry-delay`, `--ack-timeout`, or `--no-ack`.

Examples:

```sh
opennet send status online
opennet send telemetry '{"temperature":24.7}' --type json
opennet send firmware/chunk ./part.bin --type file
opennet send counter 42 --type int --host pi.local --ca lab-ca.crt
```

## Ping and benchmark

```sh
opennet ping --count 10
opennet benchmark --count 1000 --warmup 25 --payload-size 1024 --json
```

Both commands measure complete ONP round trips rather than ICMP. `benchmark`
uses acknowledged binary DATA frames.

## Connection and TLS options

- `--host` defaults to `OPENNET_HOST` or `127.0.0.1`.
- `--port` defaults to `OPENNET_PORT` or `8765`.
- `--ca` enables TLS and verifies the server against that CA.
- `--cert` and `--key` add a client identity for mutual TLS.
- `--insecure` encrypts without identity verification and is diagnostic only.
- `--allow-plaintext` deliberately permits unencrypted remote traffic.

The service also reads `OPENNET_MAX_PAYLOAD`. Command-line values take priority
over environment defaults.
