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
Authorizer = Callable[["Peer", Frame], Union[bool, Awaitable[bool]]]


class SocketLike(Protocol):
    def getsockname(self) -> object: ...


@dataclass
class Peer:
    """A connected peer passed to server handlers."""

    reader: asyncio.StreamReader
    writer: asyncio.StreamWriter
    max_payload: int
    write_timeout: float = 5.0

    @property
    def address(self) -> object:
        return self.writer.get_extra_info("peername")

    @property
    def tls_enabled(self) -> bool:
        """Return whether this peer is connected through TLS."""
        return self.writer.get_extra_info("ssl_object") is not None

    @property
    def tls_peer_certificate(self) -> Optional[dict[str, Any]]:
        """Return the verified peer certificate, when the TLS layer provides one."""
        ssl_object = self.writer.get_extra_info("ssl_object")
        if ssl_object is None:
            return None
        return cast(Optional[dict[str, Any]], ssl_object.getpeercert())

    async def send_frame(self, frame: Frame) -> None:
        await asyncio.wait_for(
            write_frame(self.writer, frame, self.max_payload),
            timeout=self.write_timeout,
        )

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
    authorization_denials: int = 0
    overloaded_messages: int = 0
    timed_out_connections: int = 0
    handler_timeouts: int = 0


class OpenNetServer:
    """ONP/1 TCP/TLS server that acknowledges accepted DATA frames."""

    def __init__(
        self,
        handler: Handler,
        *,
        host: str = "127.0.0.1",
        port: int = 8765,
        ssl_context: Optional[ssl.SSLContext] = None,
        authorizer: Optional[Authorizer] = None,
        max_payload: int = DEFAULT_MAX_PAYLOAD,
        max_connections: int = 128,
        deduplication_window: int = 4096,
        max_handler_tasks: int = 16,
        idle_timeout: float = 60.0,
        header_timeout: float = 5.0,
        body_timeout: float = 5.0,
        min_body_bytes_per_second: float = 1024.0,
        write_timeout: float = 5.0,
        handler_timeout: float = 30.0,
        ssl_handshake_timeout: float = 10.0,
    ) -> None:
        if not 0 <= port <= 65535:
            raise ValueError("port must be between 0 and 65535")
        if max_payload < 0:
            raise ValueError("max_payload must be non-negative")
        if max_connections <= 0:
            raise ValueError("max_connections must be positive")
        if deduplication_window <= 0:
            raise ValueError("deduplication_window must be positive")
        if max_handler_tasks <= 0:
            raise ValueError("max_handler_tasks must be positive")
        if any(
            value <= 0
            for value in (
                idle_timeout,
                header_timeout,
                body_timeout,
                min_body_bytes_per_second,
                write_timeout,
                handler_timeout,
                ssl_handshake_timeout,
            )
        ):
            raise ValueError("timeouts and minimum body rate must be positive")
        self.handler = handler
        self.host = host
        self.port = port
        self.ssl_context = ssl_context
        self.authorizer = authorizer
        self.max_payload = max_payload
        self.max_connections = max_connections
        self.deduplication_window = deduplication_window
        self.max_handler_tasks = max_handler_tasks
        self.idle_timeout = idle_timeout
        self.header_timeout = header_timeout
        self.body_timeout = body_timeout
        self.min_body_bytes_per_second = min_body_bytes_per_second
        self.write_timeout = write_timeout
        self.handler_timeout = handler_timeout
        self.ssl_handshake_timeout = ssl_handshake_timeout
        self.stats = ServerStats()
        self._server: Optional[asyncio.AbstractServer] = None
        self._peers: set[asyncio.StreamWriter] = set()
        self._connection_tasks: set[asyncio.Task[None]] = set()

    @property
    def sockets(self) -> list[SocketLike]:
        sockets = getattr(self._server, "sockets", None)
        return list(cast(tuple[SocketLike, ...], sockets or ()))

    async def start(self) -> None:
        if self._server is not None:
            return
        self._server = await asyncio.start_server(
            self._accept,
            self.host,
            self.port,
            ssl=self.ssl_context,
            ssl_handshake_timeout=(
                self.ssl_handshake_timeout if self.ssl_context is not None else None
            ),
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
        current = asyncio.current_task()
        tasks = [task for task in self._connection_tasks if task is not current]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

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
        connection_task = asyncio.current_task()
        if connection_task is not None:
            self._connection_tasks.add(connection_task)
        self.stats.accepted_connections += 1
        self.stats.active_connections += 1
        sock = writer.get_extra_info("socket")
        if sock is not None:
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        peer = Peer(reader, writer, self.max_payload, self.write_timeout)
        seen: set[int] = set()
        seen_order: Deque[int] = deque()
        handler_tasks: set[asyncio.Task[None]] = set()
        try:
            while True:
                frame = await read_frame(
                    reader,
                    self.max_payload,
                    idle_timeout=self.idle_timeout,
                    header_timeout=self.header_timeout,
                    body_timeout=self.body_timeout,
                    min_body_bytes_per_second=self.min_body_bytes_per_second,
                )
                if frame.kind is FrameKind.CLOSE:
                    break
                if frame.kind is FrameKind.PING:
                    await peer.send_frame(Frame(FrameKind.PONG))
                    continue
                if frame.kind is not FrameKind.DATA:
                    continue
                self.stats.received_messages += 1
                if self.authorizer is not None:
                    try:
                        decision = self.authorizer(peer, frame)
                        if inspect.isawaitable(decision):
                            decision = await decision
                        authorized = decision is True
                    except Exception:
                        authorized = False
                    if not authorized:
                        self.stats.authorization_denials += 1
                        await peer.send_frame(
                            Frame(
                                FrameKind.ERROR,
                                ValueType.UTF8,
                                payload=b"message not authorized",
                            )
                        )
                        break
                duplicate = frame.message_id in seen
                if duplicate:
                    self.stats.duplicate_messages += 1
                else:
                    if len(handler_tasks) >= self.max_handler_tasks:
                        self.stats.overloaded_messages += 1
                        await peer.send_frame(
                            Frame(
                                FrameKind.ERROR,
                                ValueType.UTF8,
                                payload=b"handler queue full",
                            )
                        )
                        break
                    seen.add(frame.message_id)
                    seen_order.append(frame.message_id)
                    if len(seen_order) > self.deduplication_window:
                        seen.discard(seen_order.popleft())
                if frame.flags & Flags.ACK_REQUIRED:
                    await peer.send_frame(
                        Frame(
                            FrameKind.ACK,
                            message_id=frame.message_id,
                            flags=Flags.DUPLICATE if duplicate else Flags.NONE,
                        )
                    )
                if not duplicate:
                    task = asyncio.create_task(
                        self._run_handler(peer, frame),
                        name=f"opennet-handler-{frame.message_id}",
                    )
                    handler_tasks.add(task)
                    task.add_done_callback(handler_tasks.discard)
        except asyncio.TimeoutError:
            self.stats.timed_out_connections += 1
        except (asyncio.IncompleteReadError, ConnectionError, ProtocolError):
            pass
        finally:
            if handler_tasks:
                await asyncio.gather(*handler_tasks, return_exceptions=True)
            self._peers.discard(writer)
            if connection_task is not None:
                self._connection_tasks.discard(connection_task)
            self.stats.active_connections -= 1
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()

    async def _run_handler(self, peer: Peer, frame: Frame) -> None:
        try:
            if inspect.iscoroutinefunction(self.handler):
                awaitable_result: Optional[Awaitable[None]] = self.handler(peer, frame)
            else:
                sync_handler = cast(Callable[[Peer, Frame], object], self.handler)
                thread_result = await asyncio.wait_for(
                    asyncio.to_thread(sync_handler, peer, frame),
                    timeout=self.handler_timeout,
                )
                awaitable_result = cast(Optional[Awaitable[None]], thread_result)
            if awaitable_result is not None:
                await asyncio.wait_for(awaitable_result, timeout=self.handler_timeout)
        except asyncio.TimeoutError:
            self.stats.handler_timeouts += 1
        except Exception:
            self.stats.handler_errors += 1
