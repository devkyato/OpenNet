import asyncio

from opennet import Frame, FrameKind, OpenNetClient, OpenNetServer, decode_value


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
        from opennet.stream import read_frame

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
