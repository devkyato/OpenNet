"""Operational command-line interface for OpenNet."""

from __future__ import annotations

import argparse
import asyncio
import ipaddress
import json
import logging
import os
import ssl
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Sequence

from . import __version__
from .client import OpenNetClient
from .protocol import DeliveryTimeout, Frame, decode_value
from .server import OpenNetServer, Peer

DEFAULT_HOST = os.environ.get("OPENNET_HOST", "127.0.0.1")
DEFAULT_PORT = int(os.environ.get("OPENNET_PORT", "8765"))
DEFAULT_MAX_PAYLOAD = int(os.environ.get("OPENNET_MAX_PAYLOAD", str(1024 * 1024)))


def _add_connection_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--ca", type=Path, help="CA certificate bundle for TLS")
    parser.add_argument("--cert", type=Path, help="client certificate for mutual TLS")
    parser.add_argument("--key", type=Path, help="client private key for mutual TLS")
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="use TLS without certificate verification (development only)",
    )
    parser.add_argument(
        "--allow-plaintext",
        action="store_true",
        help="allow unencrypted traffic to a non-loopback host",
    )
    parser.add_argument("--connect-timeout", type=float, default=10.0)
    parser.add_argument("--ack-timeout", type=float, default=5.0)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="opennet",
        description="Send, serve, diagnose, and benchmark ONP/1 connections",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    serve = commands.add_parser("serve", help="run an ONP/1 server")
    serve.add_argument("--host", default=DEFAULT_HOST)
    serve.add_argument("--port", type=int, default=DEFAULT_PORT)
    serve.add_argument("--max-payload", type=int, default=DEFAULT_MAX_PAYLOAD)
    serve.add_argument("--max-connections", type=int, default=128)
    serve.add_argument("--deduplication-window", type=int, default=4096)
    serve.add_argument("--tls-cert", type=Path)
    serve.add_argument("--tls-key", type=Path)
    serve.add_argument(
        "--tls-client-ca",
        type=Path,
        help="CA used to require and verify client certificates (mutual TLS)",
    )
    serve.add_argument(
        "--allow-plaintext",
        action="store_true",
        help="allow an unencrypted listener on a non-loopback address",
    )
    serve.add_argument(
        "--echo", action="store_true", help="send each accepted value back to its peer"
    )

    send = commands.add_parser("send", help="send one typed value and await its ACK")
    _add_connection_options(send)
    send.add_argument("topic")
    send.add_argument("value", nargs="?")
    send.add_argument(
        "--type",
        choices=("text", "json", "int", "float", "bool", "null", "hex", "file"),
        default="text",
    )
    send.add_argument("--retries", type=int, default=2)
    send.add_argument("--retry-delay", type=float, default=0.1)
    send.add_argument("--no-ack", action="store_true")

    ping = commands.add_parser("ping", help="measure ONP/1 ping/pong latency")
    _add_connection_options(ping)
    ping.add_argument("--count", type=int, default=5)
    ping.add_argument("--interval", type=float, default=0.2)

    benchmark = commands.add_parser(
        "benchmark", help="measure acknowledged loopback message latency"
    )
    _add_connection_options(benchmark)
    benchmark.add_argument("--count", type=int, default=100)
    benchmark.add_argument("--warmup", type=int, default=10)
    benchmark.add_argument("--payload-size", type=int, default=64)
    benchmark.add_argument("--retries", type=int, default=1)
    benchmark.add_argument("--json", action="store_true", dest="json_output")

    return parser


def _client_ssl(args: argparse.Namespace) -> ssl.SSLContext | None:
    if (args.cert is None) != (args.key is None):
        raise ValueError("--cert and --key must be used together")
    if args.ca is None and not args.insecure:
        if args.cert is not None:
            raise ValueError("--cert/--key require --ca")
        return None
    context = ssl.create_default_context(cafile=str(args.ca) if args.ca else None)
    if args.insecure:
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    if args.cert is not None:
        context.load_cert_chain(args.cert, args.key)
    return context


def _server_ssl(args: argparse.Namespace) -> ssl.SSLContext | None:
    if args.tls_cert is None and args.tls_key is None:
        if args.tls_client_ca is not None:
            raise ValueError("--tls-client-ca requires --tls-cert and --tls-key")
        return None
    if args.tls_cert is None or args.tls_key is None:
        raise ValueError("--tls-cert and --tls-key must be used together")
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(args.tls_cert, args.tls_key)
    if args.tls_client_ca is not None:
        context.load_verify_locations(args.tls_client_ca)
        context.verify_mode = ssl.CERT_REQUIRED
    return context


def _is_loopback(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _require_secure_remote(host: str, tls: bool, allow_plaintext: bool) -> None:
    if not tls and not allow_plaintext and not _is_loopback(host):
        raise ValueError(
            "plaintext is restricted to loopback; configure TLS or pass "
            "--allow-plaintext for a trusted development network"
        )


def _client(args: argparse.Namespace) -> OpenNetClient:
    ssl_context = _client_ssl(args)
    _require_secure_remote(args.host, ssl_context is not None, args.allow_plaintext)
    return OpenNetClient(
        args.host,
        args.port,
        ssl_context=ssl_context,
        connect_timeout=args.connect_timeout,
        ack_timeout=args.ack_timeout,
    )


def _value_from_args(args: argparse.Namespace) -> Any:
    value = args.value
    if args.type == "null":
        if value is not None:
            raise ValueError("--type null does not accept a value")
        return None
    if value is None:
        raise ValueError(f"--type {args.type} requires a value")
    if args.type == "text":
        return value
    if args.type == "json":
        return json.loads(value)
    if args.type == "int":
        return int(value)
    if args.type == "float":
        return float(value)
    if args.type == "bool":
        normalized = value.lower()
        if normalized not in {"true", "false"}:
            raise ValueError("boolean value must be true or false")
        return normalized == "true"
    if args.type == "hex":
        return bytes.fromhex(value)
    if args.type == "file":
        return Path(value).read_bytes()
    raise AssertionError(f"unhandled value type {args.type}")


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * fraction)))
    return ordered[index]


def _metrics(samples_ms: list[float], payload_size: int = 0) -> dict[str, float | int]:
    total_seconds = sum(samples_ms) / 1000.0
    return {
        "count": len(samples_ms),
        "payload_bytes": payload_size,
        "mean_ms": round(statistics.fmean(samples_ms), 3),
        "p50_ms": round(_percentile(samples_ms, 0.50), 3),
        "p95_ms": round(_percentile(samples_ms, 0.95), 3),
        "min_ms": round(min(samples_ms), 3),
        "max_ms": round(max(samples_ms), 3),
        "messages_per_second": (
            round(len(samples_ms) / total_seconds, 1)
            if total_seconds > 0
            else float("inf")
        ),
    }


async def _serve(args: argparse.Namespace) -> None:
    next_server_message_id = 1

    async def log_message(peer: Peer, frame: Frame) -> None:
        nonlocal next_server_message_id
        value = decode_value(frame.value_type, frame.payload)
        summary = (
            {"bytes": len(value)} if isinstance(value, bytes) else {"value": value}
        )
        logging.info(
            "%s",
            json.dumps(
                {
                    "peer": str(peer.address),
                    "id": frame.message_id,
                    "topic": frame.topic,
                    **summary,
                },
                ensure_ascii=False,
                default=str,
            ),
        )
        if args.echo:
            await peer.send_value(frame.topic, value, next_server_message_id)
            next_server_message_id = (
                1 if next_server_message_id == 0xFFFFFFFF else next_server_message_id + 1
            )

    ssl_context = _server_ssl(args)
    _require_secure_remote(args.host, ssl_context is not None, args.allow_plaintext)
    server = OpenNetServer(
        log_message,
        host=args.host,
        port=args.port,
        ssl_context=ssl_context,
        max_payload=args.max_payload,
        max_connections=args.max_connections,
        deduplication_window=args.deduplication_window,
    )
    await server.start()
    bound = ", ".join(str(sock.getsockname()) for sock in server.sockets)
    logging.info("OpenNet server listening on %s", bound)
    await server.serve_forever()


async def _send(args: argparse.Namespace) -> None:
    value = _value_from_args(args)
    async with _client(args) as client:
        message_id = await client.send(
            args.topic,
            value,
            require_ack=not args.no_ack,
            retries=args.retries,
            retry_delay=args.retry_delay,
        )
    print(
        json.dumps(
            {
                "status": "sent" if args.no_ack else "acknowledged",
                "message_id": message_id,
                "topic": args.topic,
            }
        )
    )


async def _ping(args: argparse.Namespace) -> None:
    if args.count <= 0:
        raise ValueError("--count must be positive")
    samples: list[float] = []
    async with _client(args) as client:
        for index in range(args.count):
            started = time.perf_counter()
            await client.ping(timeout=args.ack_timeout)
            elapsed = (time.perf_counter() - started) * 1000
            samples.append(elapsed)
            print(f"pong {index + 1}/{args.count}: {elapsed:.3f} ms")
            if index + 1 < args.count and args.interval:
                await asyncio.sleep(args.interval)
    print(json.dumps(_metrics(samples), sort_keys=True))


async def _benchmark(args: argparse.Namespace) -> None:
    if args.count <= 0 or args.warmup < 0 or args.payload_size < 0:
        raise ValueError("count must be positive; warmup and payload size cannot be negative")
    payload = bytes((index % 251 for index in range(args.payload_size)))
    samples: list[float] = []
    async with _client(args) as client:
        for _ in range(args.warmup):
            await client.send(
                "_opennet/benchmark", payload, retries=args.retries, retry_delay=0
            )
        for _ in range(args.count):
            started = time.perf_counter()
            await client.send(
                "_opennet/benchmark", payload, retries=args.retries, retry_delay=0
            )
            samples.append((time.perf_counter() - started) * 1000)
    metrics = _metrics(samples, args.payload_size)
    if args.json_output:
        print(json.dumps(metrics, sort_keys=True))
    else:
        for key, value in metrics.items():
            print(f"{key}: {value}")


async def run(args: argparse.Namespace) -> None:
    if args.command == "serve":
        await _serve(args)
    elif args.command == "send":
        await _send(args)
    elif args.command == "ping":
        await _ping(args)
    elif args.command == "benchmark":
        await _benchmark(args)
    else:
        raise AssertionError(f"unknown command {args.command}")


def main(argv: Sequence[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    try:
        asyncio.run(run(args))
    except (ConnectionError, DeliveryTimeout, OSError, ValueError) as exc:
        parser.exit(1, f"opennet: {exc}\n")


def server_main() -> None:
    """Backward-compatible entry point for the v0.1.0 command name."""
    main(("serve", *sys.argv[1:]))


if __name__ == "__main__":
    main()
