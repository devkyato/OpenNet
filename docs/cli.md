# Command-line reference

`opennet --help` exposes four commands.

## Serve

```sh
opennet serve [--host HOST] [--port PORT] [--echo]
```

Useful controls include `--max-payload`, `--max-connections`,
`--deduplication-window`, `--tls-cert`, `--tls-key`, and `--tls-client-ca`.
Remote plaintext listeners require `--allow-plaintext`. Logs contain message
metadata and payload size by default; `--log-values` is an explicit
secret-exposure opt-in.

Repeat `--allow-topic-prefix PREFIX` to apply one shared allowlist to every
client. For example, `--allow-topic-prefix sensor/ --allow-topic-prefix status/`
rejects other topics before the handler and ACK. This simple CLI policy does not
map individual certificates to different topics. Use the Python
`OpenNetServer` `authorizer` API for identity-specific rules.

## Send

```sh
opennet send TOPIC [VALUE] [--type TYPE]
```

Types are `text`, `json`, `int`, `float`, `bool`, `null`, `hex`, and `file`.
The command waits for an ACK by default and retries twice. Adjust with
`--retries`, `--retry-delay`, `--ack-timeout`, or `--no-ack`.
For `--type file`, the CLI checks the file size against `--max-payload` before
reading it.

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
uses one sequential acknowledged binary DATA frame at a time. Its
`messages_per_second` value is the reciprocal of those sampled round trips, not
maximum concurrent throughput; JSON output labels the mode
`sequential_acknowledged`.

## Connection and TLS options

- `--host` defaults to `OPENNET_HOST` or `127.0.0.1`.
- `--port` defaults to `OPENNET_PORT` or `8765`.
- `--ca` enables TLS and verifies the server against that CA.
- `--cert` and `--key` add a client identity for mutual TLS.
- `--insecure` encrypts without identity verification and is diagnostic only.
- `--allow-plaintext` deliberately permits unencrypted remote traffic.

The service also reads `OPENNET_MAX_PAYLOAD`. Command-line values take priority
over environment defaults.
