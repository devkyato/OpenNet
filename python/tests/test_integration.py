import asyncio

import pytest

from opennet import Flags, Frame, FrameKind, OpenNetClient, OpenNetServer, decode_value
from opennet.stream import read_frame, write_frame


async def test_client_server_ack_and_values():
    received: asyncio.Queue[tuple[str, object]] = asyncio.Queue()

    async def handler(_peer, frame: Frame):
        await received.put((frame.topic, decode_value(frame.value_type, frame.payload)))

    server = OpenNetServer(handler, host="127.0.0.1", port=0)
    await server.start()
    port = server.sockets[0].getsockname()[1]  # type: ignore[union-attr]
    try:
        async with OpenNetClient("127.0.0.1", port) as client:
            message_id = await client.send("lab/temperature", {"celsius": 24.5})
            assert message_id == 1
            assert await asyncio.wait_for(received.get(), 1) == (
                "lab/temperature",
                {"celsius": 24.5},
            )
            await client.ping(timeout=1)
    finally:
        await server.close()


async def test_duplicate_data_is_delivered_once_and_acknowledged_twice():
    calls = 0
    ack_count = 0

    async def handler(_peer, _frame):
        nonlocal calls
        calls += 1

    server = OpenNetServer(handler, host="127.0.0.1", port=0)
    await server.start()
    port = server.sockets[0].getsockname()[1]  # type: ignore[union-attr]
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    frame = Frame(
        FrameKind.DATA,
        topic="event",
        payload=b"",
        message_id=7,
        flags=1,
    )
    try:
        writer.write(frame.to_bytes() + frame.to_bytes())
        await writer.drain()
        for _ in range(2):
            ack = await asyncio.wait_for(read_frame(reader), 1)
            assert ack.kind is FrameKind.ACK
            ack_count += 1
        assert calls == 1
        assert ack_count == 2
    finally:
        writer.close()
        await writer.wait_closed()
        await server.close()


async def test_client_retries_with_same_id_and_duplicate_flag():
    attempts: list[Frame] = []

    async def accept(reader, writer):
        first = await read_frame(reader)
        attempts.append(first)
        second = await read_frame(reader)
        attempts.append(second)
        await write_frame(
            writer, Frame(FrameKind.ACK, message_id=second.message_id), 1024
        )
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(accept, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        client = OpenNetClient("127.0.0.1", port, ack_timeout=0.02)
        await client.connect()
        message_id = await client.send(
            "retry/test", "value", retries=1, retry_delay=0
        )
        assert message_id == 1
        assert [frame.message_id for frame in attempts] == [1, 1]
        assert attempts[0].flags == Flags.ACK_REQUIRED
        assert attempts[1].flags == Flags.ACK_REQUIRED | Flags.DUPLICATE
        await client.close()
    finally:
        server.close()
        await server.wait_closed()


async def test_receive_raises_when_remote_closes():
    async def accept(_reader, writer):
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(accept, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        client = OpenNetClient("127.0.0.1", port)
        await client.connect()
        with pytest.raises(ConnectionError, match="closed"):
            await client.receive(timeout=1)
        await client.close()
    finally:
        server.close()
        await server.wait_closed()


async def test_server_deduplication_window_is_bounded():
    delivered: list[int] = []

    async def handler(_peer, frame):
        delivered.append(frame.message_id)

    server = OpenNetServer(
        handler,
        host="127.0.0.1",
        port=0,
        deduplication_window=2,
    )
    await server.start()
    port = server.sockets[0].getsockname()[1]  # type: ignore[union-attr]
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    try:
        for message_id in (1, 2, 1, 3, 1):
            await write_frame(
                writer,
                Frame(
                    FrameKind.DATA,
                    topic="dedup/test",
                    message_id=message_id,
                    flags=Flags.ACK_REQUIRED,
                ),
                1024,
            )
            ack = await asyncio.wait_for(read_frame(reader), 1)
            assert ack.kind is FrameKind.ACK
        assert delivered == [1, 2, 3, 1]
        assert server.stats.received_messages == 5
        assert server.stats.duplicate_messages == 1
    finally:
        writer.close()
        await writer.wait_closed()
        await server.close()
