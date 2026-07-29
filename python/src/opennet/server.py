"""Async OpenNet server."""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import socket
import ssl
from collections import deque
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Deque, Optional, Protocol, Union, cast

from .protocol import (
    DEFAULT_MAX_PAYLOAD,
    Flags,
    Frame,
    FrameKind,
    ProtocolError,
    ValueType,
    encode_value,
)
from .stream import read_frame, write_frame

Handler = Callable[["Peer", Frame], Union[None, Awaitable[None]]]


class SocketLike(Protocol):
    def getsockname(self) -> object: ...


@dataclass
class Peer:
    """A connected peer passed to server handlers."""

    reader: asyncio.StreamReader
    writer: asyncio.StreamWriter
    max_payload: int

    @property
    def address(self) -> object:
        return self.writer.get_extra_info("peername")

    async def send_frame(self, frame: Frame) -> None:
        await write_frame(self.writer, frame, self.max_payload)

    async def send(
        self, topic: str, payload: bytes, message_id: int, value_type: ValueType
    ) -> None:
        await self.send_frame(
            Frame(FrameKind.DATA, value_type, topic, payload, message_id)
        )

    async def send_value(self, topic: str, value: Any, message_id: int) -> None:
        """Encode and send a typed value to this peer without requesting an ACK."""
        value_type, payload = encode_value(value)
        await self.send(topic, payload, message_id, value_type)

    async def close(self) -> None:
        if not self.writer.is_closing():
            with contextlib.suppress(Exception):
                await self.send_frame(Frame(FrameKind.CLOSE))
            self.writer.close()
            with contextlib.suppress(Exception):
                await self.writer.wait_closed()


@dataclass
class ServerStats:
    """Process-local counters for operational visibility."""

    accepted_connections: int = 0
    active_connections: int = 0
    rejected_connections: int = 0
    received_messages: int = 0
    duplicate_messages: int = 0
    handler_errors: int = 0


class OpenNetServer:
    """ONP/1 TCP/TLS server that acknowledges accepted DATA frames."""

    def __init__(
        self,
        handler: Handler,
        *,
        host: str = "127.0.0.1",
        port: int = 8765,
        ssl_context: Optional[ssl.SSLContext] = None,
        max_payload: int = DEFAULT_MAX_PAYLOAD,
        max_connections: int = 128,
        deduplication_window: int = 4096,
    ) -> None:
        if not 0 <= port <= 65535:
            raise ValueError("port must be between 0 and 65535")
        if max_payload < 0:
            raise ValueError("max_payload must be non-negative")
        if max_connections <= 0:
            raise ValueError("max_connections must be positive")
        if deduplication_window <= 0:
            raise ValueError("deduplication_window must be positive")
        self.handler = handler
        self.host = host
        self.port = port
        self.ssl_context = ssl_context
        self.max_payload = max_payload
        self.max_connections = max_connections
        self.deduplication_window = deduplication_window
        self.stats = ServerStats()
        self._server: Optional[asyncio.AbstractServer] = None
        self._peers: set[asyncio.StreamWriter] = set()

    @property
    def sockets(self) -> list[SocketLike]:
        sockets = getattr(self._server, "sockets", None)
        return list(cast(tuple[SocketLike, ...], sockets or ()))

    async def start(self) -> None:
        if self._server is not None:
            return
        self._server = await asyncio.start_server(
            self._accept, self.host, self.port, ssl=self.ssl_context
        )

    async def serve_forever(self) -> None:
        await self.start()
        assert self._server is not None
        async with self._server:
            await self._server.serve_forever()

    async def close(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        writers = list(self._peers)
        for writer in writers:
            writer.close()
        await asyncio.gather(
            *(writer.wait_closed() for writer in writers), return_exceptions=True
        )

    async def __aenter__(self) -> "OpenNetServer":
        await self.start()
        return self

    async def __aexit__(self, *_args: object) -> None:
        await self.close()

    async def _accept(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        if len(self._peers) >= self.max_connections:
            self.stats.rejected_connections += 1
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()
            return
        self._peers.add(writer)
        self.stats.accepted_connections += 1
        self.stats.active_connections += 1
        sock = writer.get_extra_info("socket")
        if sock is not None:
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        peer = Peer(reader, writer, self.max_payload)
        seen: set[int] = set()
        seen_order: Deque[int] = deque()
        try:
            while True:
                frame = await read_frame(reader, self.max_payload)
                if frame.kind is FrameKind.CLOSE:
                    break
                if frame.kind is FrameKind.PING:
                    await peer.send_frame(Frame(FrameKind.PONG))
                    continue
                if frame.kind is not FrameKind.DATA:
                    continue
                self.stats.received_messages += 1
                duplicate = frame.message_id in seen
                if duplicate:
                    self.stats.duplicate_messages += 1
                else:
                    seen.add(frame.message_id)
                    seen_order.append(frame.message_id)
                    if len(seen_order) > self.deduplication_window:
                        seen.discard(seen_order.popleft())
                if not duplicate:
                    try:
                        result = self.handler(peer, frame)
                        if inspect.isawaitable(result):
                            await result
                    except Exception:
                        self.stats.handler_errors += 1
                        await peer.send_frame(
                            Frame(
                                FrameKind.ERROR,
                                ValueType.UTF8,
                                payload=b"application handler failed",
                            )
                        )
                        break
                if frame.flags & Flags.ACK_REQUIRED:
                    await peer.send_frame(
                        Frame(
                            FrameKind.ACK,
                            message_id=frame.message_id,
                            flags=Flags.DUPLICATE if duplicate else Flags.NONE,
                        )
                    )
        except (asyncio.IncompleteReadError, ConnectionError, ProtocolError):
            pass
        finally:
            self._peers.discard(writer)
            self.stats.active_connections -= 1
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()
