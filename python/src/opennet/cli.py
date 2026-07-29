"""Small observable OpenNet development server."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging

from .protocol import Frame, decode_value
from .server import OpenNetServer, Peer


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run an ONP/1 development server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--max-payload", type=int, default=1024 * 1024)
    return parser.parse_args()


async def run(args: argparse.Namespace) -> None:
    async def log_message(peer: Peer, frame: Frame) -> None:
        value = decode_value(frame.value_type, frame.payload)
        summary = (
            f"<{len(value)} bytes>" if isinstance(value, bytes) else repr(value)
        )
        logging.info(
            "%s id=%d topic=%s value=%s",
            peer.address,
            frame.message_id,
            frame.topic,
            summary,
        )

    server = OpenNetServer(
        log_message, host=args.host, port=args.port, max_payload=args.max_payload
    )
    logging.info("listening on %s:%d", args.host, args.port)
    await server.serve_forever()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(run(parse_args()))


if __name__ == "__main__":
    main()
