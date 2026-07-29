"""Reproducible ONP/1 TCP/TLS loopback latency and load benchmark."""

from __future__ import annotations

import argparse
import asyncio
import json
import platform
import ssl
import statistics
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python" / "src"))

from opennet import OpenNetClient, OpenNetServer


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[round((len(ordered) - 1) * fraction)]


def summarize(
    samples: list[float], payload_size: int, clients: int, elapsed: float
) -> dict[str, Any]:
    return {
        "payload_bytes": payload_size,
        "clients": clients,
        "messages": len(samples),
        "mean_ms": round(statistics.fmean(samples), 3),
        "p50_ms": round(percentile(samples, 0.50), 3),
        "p95_ms": round(percentile(samples, 0.95), 3),
        "max_ms": round(max(samples), 3),
        "messages_per_second": round(len(samples) / elapsed, 1),
    }


async def one_run(
    *,
    payload_size: int,
    messages: int,
    clients: int,
    server_ssl: ssl.SSLContext | None,
    client_ssl: ssl.SSLContext | None,
) -> dict[str, Any]:
    server = OpenNetServer(lambda _peer, _frame: None, port=0, ssl_context=server_ssl)
    await server.start()
    address = server.sockets[0].getsockname()
    port = int(address[1])  # type: ignore[index]
    samples: list[float] = []
    payload = bytes(index % 251 for index in range(payload_size))

    async def worker(count: int) -> None:
        async with OpenNetClient(
            "127.0.0.1", port, ssl_context=client_ssl, ack_timeout=10
        ) as client:
            await client.send("_benchmark/warmup", payload)
            for _ in range(count):
                started = time.perf_counter()
                await client.send("_benchmark/data", payload)
                samples.append((time.perf_counter() - started) * 1000)

    counts = [messages // clients + (1 if index < messages % clients else 0) for index in range(clients)]
    started = time.perf_counter()
    await asyncio.gather(*(worker(count) for count in counts if count))
    elapsed = time.perf_counter() - started
    await server.close()
    result = summarize(samples, payload_size, clients, elapsed)
    result["server_received"] = server.stats.received_messages
    return result


def tls_contexts(args: argparse.Namespace) -> tuple[ssl.SSLContext | None, ssl.SSLContext | None]:
    if args.cert is None:
        return None, None
    if args.key is None or args.ca is None:
        raise SystemExit("--cert, --key, and --ca are required together")
    server = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server.load_cert_chain(args.cert, args.key)
    client = ssl.create_default_context(cafile=str(args.ca))
    client.check_hostname = False
    return server, client


async def run(args: argparse.Namespace) -> dict[str, Any]:
    server_ssl, client_ssl = tls_contexts(args)
    results = []
    for size in args.payload_sizes:
        results.append(
            await one_run(
                payload_size=size,
                messages=args.messages,
                clients=args.clients,
                server_ssl=server_ssl,
                client_ssl=client_ssl,
            )
        )
    return {
        "schema": 1,
        "transport": "TLS 1.2+" if server_ssl else "TCP",
        "environment": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "processor": platform.processor() or "not reported",
        },
        "method": "IPv4 loopback; one warm-up message per client; ACK round-trip timing",
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--messages", type=int, default=1000)
    parser.add_argument("--clients", type=int, default=1)
    parser.add_argument("--payload-sizes", type=int, nargs="+", default=[0, 64, 1024, 65536])
    parser.add_argument("--cert", type=Path)
    parser.add_argument("--key", type=Path)
    parser.add_argument("--ca", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.messages <= 0 or args.clients <= 0 or any(size < 0 for size in args.payload_sizes):
        parser.error("messages and clients must be positive; payload sizes cannot be negative")
    text = json.dumps(asyncio.run(run(args)), indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
