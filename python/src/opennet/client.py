"""Async OpenNet client."""

from __future__ import annotations

import asyncio
import contextlib
import ssl
from types import TracebackType
from typing import Any, AsyncIterator, Optional, Type

from .protocol import (
    DEFAULT_MAX_PAYLOAD,
    DeliveryTimeout,
    Flags,
    Frame,
    FrameKind,
    ProtocolError,
    ReceiveQueueFull,
    RemoteError,
    ValueType,
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
        connect_timeout: float = 10.0,
        write_timeout: float = 5.0,
        receive_queue_size: int = 256,
    ) -> None:
        if not 1 <= port <= 65535:
            raise ValueError("port must be between 1 and 65535")
        if max_payload < 0:
            raise ValueError("max_payload must be non-negative")
        if ack_timeout <= 0 or connect_timeout <= 0 or write_timeout <= 0:
            raise ValueError("timeouts must be positive")
        if receive_queue_size <= 0:
            raise ValueError("receive_queue_size must be positive")
        self.host = host
        self.port = port
        self.ssl_context = ssl_context
        self.max_payload = max_payload
        self.ack_timeout = ack_timeout
        self.connect_timeout = connect_timeout
        self.write_timeout = write_timeout
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._next_id = 1
        self._pending: dict[int, asyncio.Future[None]] = {}
        self._messages: asyncio.Queue[Frame] = asyncio.Queue(maxsize=receive_queue_size)
        self._pong_waiters: list[asyncio.Future[None]] = []
        self._reader_task: Optional[asyncio.Task[None]] = None
        self._closed_event = asyncio.Event()
        self._reader_error: Optional[BaseException] = None

    @property
    def connected(self) -> bool:
        return self._writer is not None and not self._writer.is_closing()

    async def connect(self) -> None:
        if self.connected:
            return
        self._closed_event.clear()
        self._reader_error = None
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(self.host, self.port, ssl=self.ssl_context),
            timeout=self.connect_timeout,
        )
        self._reader = reader
        self._writer = writer
        sock = writer.get_extra_info("socket")
        if sock is not None:
            sock.setsockopt(6, 1, 1)  # IPPROTO_TCP, TCP_NODELAY
        self._reader_task = asyncio.create_task(self._read_loop(), name="opennet-reader")

    async def close(self) -> None:
        writer = self._writer
        if writer is None:
            return
        with contextlib.suppress(Exception):
            await self._write_frame(writer, Frame(FrameKind.CLOSE))
        writer.close()
        with contextlib.suppress(Exception):
            await writer.wait_closed()
        if self._reader_task is not None:
            self._reader_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reader_task
        self._reader = None
        self._writer = None
        self._reader_error = ConnectionError("OpenNet connection closed")
        self._closed_event.set()
        self._fail_pending(ConnectionError("OpenNet connection closed"))

    async def send(
        self,
        topic: str,
        value: Any,
        *,
        require_ack: bool = True,
        retries: int = 0,
        retry_delay: float = 0.1,
    ) -> int:
        if retries < 0:
            raise ValueError("retries must be non-negative")
        if retry_delay < 0:
            raise ValueError("retry_delay must be non-negative")
        writer = self._require_writer()
        value_type, payload = encode_value(value)
        message_id = self._next_message_id()
        base_flags = Flags.ACK_REQUIRED if require_ack else Flags.NONE
        future: Optional[asyncio.Future[None]] = None
        if require_ack:
            future = asyncio.get_running_loop().create_future()
            self._pending[message_id] = future
        try:
            for attempt in range(retries + 1):
                if future is not None and future.done():
                    future.result()
                    return message_id
                flags = base_flags | (Flags.DUPLICATE if attempt else Flags.NONE)
                frame = Frame(
                    FrameKind.DATA, value_type, topic, payload, message_id, flags
                )
                await self._write_frame(writer, frame)
                if future is None:
                    return message_id
                try:
                    await asyncio.wait_for(
                        asyncio.shield(future), timeout=self.ack_timeout
                    )
                    return message_id
                except asyncio.TimeoutError:
                    if attempt == retries:
                        raise DeliveryTimeout(message_id, attempt + 1) from None
                    if retry_delay:
                        await asyncio.sleep(retry_delay * (2**attempt))
        finally:
            pending = self._pending.pop(message_id, None)
            if pending is not None and not pending.done():
                pending.cancel()
        raise AssertionError("unreachable")

    async def receive(self, timeout: Optional[float] = None) -> Frame:
        if self._closed_event.is_set() and self._messages.empty():
            raise self._connection_error()

        message_task = asyncio.create_task(self._messages.get())
        closed_task = asyncio.create_task(self._closed_event.wait())
        try:
            done, _pending = await asyncio.wait(
                (message_task, closed_task),
                timeout=timeout,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if message_task in done:
                return message_task.result()
            if not done:
                raise asyncio.TimeoutError
            if not self._messages.empty():
                return self._messages.get_nowait()
            raise self._connection_error()
        finally:
            for task in (message_task, closed_task):
                if not task.done():
                    task.cancel()

    async def messages(self) -> AsyncIterator[Frame]:
        while self.connected or not self._messages.empty():
            yield await self.receive()

    async def ping(self, timeout: float = 5.0) -> None:
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        writer = self._require_writer()
        waiter: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        self._pong_waiters.append(waiter)
        try:
            await self._write_frame(writer, Frame(FrameKind.PING))
            await asyncio.wait_for(asyncio.shield(waiter), timeout)
        finally:
            if waiter in self._pong_waiters:
                self._pong_waiters.remove(waiter)

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
        start = self._next_id
        message_id = start
        while message_id in self._pending:
            message_id = 1 if message_id == 0xFFFFFFFF else message_id + 1
            if message_id == start:
                raise RuntimeError("all ONP/1 message IDs are pending")
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
                    await self._write_frame(self._writer, Frame(FrameKind.PONG))
                elif frame.kind is FrameKind.PONG:
                    if self._pong_waiters:
                        waiter = self._pong_waiters.pop(0)
                        if not waiter.done():
                            waiter.set_result(None)
                elif frame.kind is FrameKind.CLOSE:
                    return
                elif frame.kind is FrameKind.ERROR:
                    reason = frame.payload.decode("utf-8", errors="replace")
                    raise RemoteError(reason or "unspecified error")
                elif frame.kind is FrameKind.DATA:
                    try:
                        self._messages.put_nowait(frame)
                    except asyncio.QueueFull:
                        with contextlib.suppress(Exception):
                            await self._write_frame(
                                self._writer,
                                Frame(
                                    FrameKind.ERROR,
                                    value_type=ValueType.UTF8,
                                    payload=b"receive queue full",
                                ),
                            )
                        raise ReceiveQueueFull(
                            "OpenNet receive queue is full"
                        ) from None
        except (
            asyncio.IncompleteReadError,
            asyncio.TimeoutError,
            ConnectionError,
            ProtocolError,
        ) as exc:
            self._reader_error = exc
            self._fail_pending(exc)
        finally:
            if self._reader_error is None:
                self._reader_error = ConnectionError("OpenNet peer closed")
            self._fail_pending(self._reader_error)
            self._fail_pings(self._reader_error)
            if self._writer is not None:
                self._writer.close()
            self._closed_event.set()

    def _fail_pending(self, exc: BaseException) -> None:
        for future in self._pending.values():
            if not future.done():
                future.set_exception(exc)

    def _connection_error(self) -> ConnectionError:
        if self._reader_error is None:
            return ConnectionError("OpenNet connection closed")
        error = ConnectionError("OpenNet connection closed")
        error.__cause__ = self._reader_error
        return error

    async def _write_frame(
        self, writer: asyncio.StreamWriter, frame: Frame
    ) -> None:
        await asyncio.wait_for(
            write_frame(writer, frame, self.max_payload),
            timeout=self.write_timeout,
        )

    def _fail_pings(self, exc: BaseException) -> None:
        for waiter in self._pong_waiters:
            if not waiter.done():
                waiter.set_exception(exc)
        self._pong_waiters.clear()
