"""Async OpenNet server."""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import ssl
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional, Union

from .protocol import (
    DEFAULT_MAX_PAYLOAD,
    Flags,
    Frame,
    FrameKind,
    ProtocolError,
    ValueType,
)
from .stream import read_frame, write_frame

Handler = Callable[["Peer", Frame], Union[None, Awaitable[None]]]


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

    async def close(self) -> None:
        if not self.writer.is_closing():
            with contextlib.suppress(Exception):
                await self.send_frame(Frame(FrameKind.CLOSE))
            self.writer.close()
            with contextlib.suppress(Exception):
                await self.writer.wait_closed()


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
    ) -> None:
        self.handler = handler
        self.host = host
        self.port = port
        self.ssl_context = ssl_context
        self.max_payload = max_payload
        self._server: Optional[asyncio.AbstractServer] = None
        self._peers: set[asyncio.StreamWriter] = set()

    @property
    def sockets(self) -> list[object]:
        sockets = getattr(self._server, "sockets", None)
        return list(sockets or ())

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
        self._peers.add(writer)
        peer = Peer(reader, writer, self.max_payload)
        seen: set[int] = set()
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
                duplicate = frame.message_id in seen
                seen.add(frame.message_id)
                if not duplicate:
                    result = self.handler(peer, frame)
                    if inspect.isawaitable(result):
                        await result
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
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()
