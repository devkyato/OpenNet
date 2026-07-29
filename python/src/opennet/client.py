"""Async OpenNet client."""

from __future__ import annotations

import asyncio
import contextlib
import ssl
from collections import deque
from types import TracebackType
from typing import Any, AsyncIterator, Deque, Optional, Type

from .protocol import (
    DEFAULT_MAX_PAYLOAD,
    Flags,
    Frame,
    FrameKind,
    ProtocolError,
    encode_value,
)
from .stream import read_frame, write_frame


class OpenNetClient:
    """A single ONP/1 connection with typed send/receive operations."""

    def __init__(
        self,
        host: str,
        port: int = 8765,
        *,
        ssl_context: Optional[ssl.SSLContext] = None,
        max_payload: int = DEFAULT_MAX_PAYLOAD,
        ack_timeout: float = 5.0,
    ) -> None:
        self.host = host
        self.port = port
        self.ssl_context = ssl_context
        self.max_payload = max_payload
        self.ack_timeout = ack_timeout
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._next_id = 1
        self._pending: dict[int, asyncio.Future[None]] = {}
        self._messages: asyncio.Queue[Frame] = asyncio.Queue()
        self._backlog: Deque[Frame] = deque()
        self._reader_task: Optional[asyncio.Task[None]] = None

    @property
    def connected(self) -> bool:
        return self._writer is not None and not self._writer.is_closing()

    async def connect(self) -> None:
        if self.connected:
            return
        self._reader, self._writer = await asyncio.open_connection(
            self.host, self.port, ssl=self.ssl_context
        )
        sock = self._writer.get_extra_info("socket")
        if sock is not None:
            sock.setsockopt(6, 1, 1)  # IPPROTO_TCP, TCP_NODELAY
        self._reader_task = asyncio.create_task(self._read_loop(), name="opennet-reader")

    async def close(self) -> None:
        writer = self._writer
        if writer is None:
            return
        with contextlib.suppress(Exception):
            await write_frame(writer, Frame(FrameKind.CLOSE), self.max_payload)
        writer.close()
        with contextlib.suppress(Exception):
            await writer.wait_closed()
        if self._reader_task is not None:
            self._reader_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reader_task
        self._reader = None
        self._writer = None
        self._fail_pending(ConnectionError("OpenNet connection closed"))

    async def send(
        self,
        topic: str,
        value: Any,
        *,
        require_ack: bool = True,
    ) -> int:
        writer = self._require_writer()
        value_type, payload = encode_value(value)
        message_id = self._next_message_id()
        flags = Flags.ACK_REQUIRED if require_ack else Flags.NONE
        frame = Frame(FrameKind.DATA, value_type, topic, payload, message_id, flags)
        future: Optional[asyncio.Future[None]] = None
        if require_ack:
            future = asyncio.get_running_loop().create_future()
            self._pending[message_id] = future
        try:
            await write_frame(writer, frame, self.max_payload)
            if future is not None:
                await asyncio.wait_for(future, self.ack_timeout)
        finally:
            self._pending.pop(message_id, None)
        return message_id

    async def receive(self) -> Frame:
        if self._backlog:
            return self._backlog.popleft()
        return await self._messages.get()

    async def messages(self) -> AsyncIterator[Frame]:
        while self.connected:
            yield await self.receive()

    async def ping(self, timeout: float = 5.0) -> None:
        writer = self._require_writer()
        await write_frame(writer, Frame(FrameKind.PING), self.max_payload)
        while True:
            frame = await asyncio.wait_for(self._messages.get(), timeout)
            if frame.kind is FrameKind.PONG:
                return
            self._backlog.append(frame)

    async def __aenter__(self) -> "OpenNetClient":
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        await self.close()

    def _require_writer(self) -> asyncio.StreamWriter:
        if not self.connected or self._writer is None:
            raise ConnectionError("OpenNet client is not connected")
        return self._writer

    def _next_message_id(self) -> int:
        message_id = self._next_id
        self._next_id = 1 if message_id == 0xFFFFFFFF else message_id + 1
        return message_id

    async def _read_loop(self) -> None:
        assert self._reader is not None and self._writer is not None
        try:
            while True:
                frame = await read_frame(self._reader, self.max_payload)
                if frame.kind is FrameKind.ACK:
                    future = self._pending.get(frame.message_id)
                    if future is not None and not future.done():
                        future.set_result(None)
                elif frame.kind is FrameKind.PING:
                    await write_frame(self._writer, Frame(FrameKind.PONG), self.max_payload)
                elif frame.kind is FrameKind.CLOSE:
                    return
                else:
                    await self._messages.put(frame)
        except (asyncio.IncompleteReadError, ConnectionError, ProtocolError) as exc:
            self._fail_pending(exc)
        finally:
            if self._writer is not None:
                self._writer.close()

    def _fail_pending(self, exc: BaseException) -> None:
        for future in self._pending.values():
            if not future.done():
                future.set_exception(exc)
