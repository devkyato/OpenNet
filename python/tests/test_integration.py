import asyncio
import ssl
import time
from pathlib import Path

import pytest

from opennet import (
    Flags,
    Frame,
    FrameKind,
    OpenNetClient,
    OpenNetServer,
    Peer,
    ReceiveQueueFull,
    ValueType,
    decode_value,
)
from opennet.stream import read_frame, write_frame

CERTS = Path(__file__).with_name("certs")


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
    authorization_calls = 0
    ack_count = 0

    def authorizer(_peer, _frame):
        nonlocal authorization_calls
        authorization_calls += 1
        return True

    async def handler(_peer, _frame):
        nonlocal calls
        calls += 1

    server = OpenNetServer(
        handler,
        host="127.0.0.1",
        port=0,
        authorizer=authorizer,
    )
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
        assert authorization_calls == 2
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


async def test_ping_dispatches_data_arriving_before_pong():
    async def accept(reader, writer):
        ping = await read_frame(reader)
        assert ping.kind is FrameKind.PING
        data = Frame(
            FrameKind.DATA,
            ValueType.UTF8,
            topic="status/update",
            payload=b"ready",
            message_id=41,
        )
        writer.write(data.to_bytes() + Frame(FrameKind.PONG).to_bytes())
        await writer.drain()
        await read_frame(reader)
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(accept, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        client = OpenNetClient("127.0.0.1", port)
        await client.connect()
        await client.ping(timeout=1)
        data = await client.receive(timeout=1)
        assert data.kind is FrameKind.DATA
        assert data.topic == "status/update"
        assert data.payload == b"ready"
        await client.close()
    finally:
        server.close()
        await server.wait_closed()


async def test_full_application_queue_does_not_block_ack_dispatch():
    async def accept(reader, writer):
        outbound = await read_frame(reader)
        queued = Frame(
            FrameKind.DATA,
            ValueType.UTF8,
            topic="queued/data",
            payload=b"x",
            message_id=99,
        )
        ack = Frame(FrameKind.ACK, message_id=outbound.message_id)
        writer.write(queued.to_bytes() + ack.to_bytes())
        await writer.drain()
        await read_frame(reader)
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(accept, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        client = OpenNetClient(
            "127.0.0.1",
            port,
            ack_timeout=0.5,
            receive_queue_size=1,
        )
        await client.connect()
        assert await client.send("outbound/data", "value") == 1
        queued = await client.receive(timeout=1)
        assert queued.topic == "queued/data"
        await client.close()
    finally:
        server.close()
        await server.wait_closed()


async def test_receive_queue_overflow_closes_with_explicit_error():
    async def accept(reader, writer):
        first = Frame(FrameKind.DATA, topic="queue/one", message_id=1)
        second = Frame(FrameKind.DATA, topic="queue/two", message_id=2)
        writer.write(first.to_bytes() + second.to_bytes())
        await writer.drain()
        response = await read_frame(reader)
        assert response.kind is FrameKind.ERROR
        assert response.payload == b"receive queue full"
        assert await reader.read() == b""
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(accept, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        client = OpenNetClient("127.0.0.1", port, receive_queue_size=1)
        await client.connect()
        first = await client.receive(timeout=1)
        assert first.topic == "queue/one"
        with pytest.raises(ConnectionError) as result:
            await client.receive(timeout=1)
        assert isinstance(result.value.__cause__, ReceiveQueueFull)
    finally:
        server.close()
        await server.wait_closed()


async def test_message_id_wrap_skips_pending_ids():
    client = OpenNetClient("127.0.0.1")
    loop = asyncio.get_running_loop()
    maximum = loop.create_future()
    first = loop.create_future()
    client._pending[0xFFFFFFFF] = maximum
    client._pending[1] = first
    client._next_id = 0xFFFFFFFF

    assert client._next_message_id() == 2
    assert client._next_id == 3

    maximum.cancel()
    first.cancel()


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


async def test_server_ack_and_ping_progress_before_slow_handler_finishes():
    started = asyncio.Event()
    release = asyncio.Event()

    async def handler(_peer: Peer, _frame: Frame) -> None:
        started.set()
        await release.wait()

    server = OpenNetServer(handler, host="127.0.0.1", port=0)
    await server.start()
    port = server.sockets[0].getsockname()[1]  # type: ignore[union-attr]
    try:
        async with OpenNetClient(
            "127.0.0.1",
            port,
            ack_timeout=0.1,
        ) as client:
            assert await client.send("slow/work", "value") == 1
            await asyncio.wait_for(started.wait(), 1)
            assert not release.is_set()
            await client.ping(timeout=0.2)
            release.set()
    finally:
        release.set()
        await server.close()


async def test_slow_synchronous_handler_runs_off_event_loop():
    def handler(_peer: Peer, _frame: Frame) -> None:
        time.sleep(0.15)

    server = OpenNetServer(handler, host="127.0.0.1", port=0)
    await server.start()
    port = server.sockets[0].getsockname()[1]  # type: ignore[union-attr]
    try:
        async with OpenNetClient("127.0.0.1", port) as client:
            assert await client.send("sync/work", "value") == 1
            await client.ping(timeout=0.1)
    finally:
        await server.close()


async def test_handler_side_effect_then_exception_does_not_revoke_ack():
    side_effect = asyncio.Event()

    async def handler(_peer: Peer, _frame: Frame) -> None:
        side_effect.set()
        raise RuntimeError("failed after side effect")

    server = OpenNetServer(handler, host="127.0.0.1", port=0)
    await server.start()
    port = server.sockets[0].getsockname()[1]  # type: ignore[union-attr]
    try:
        async with OpenNetClient("127.0.0.1", port) as client:
            assert await client.send("effect/work", "value") == 1
            await asyncio.wait_for(side_effect.wait(), 1)
            for _ in range(20):
                if server.stats.handler_errors == 1:
                    break
                await asyncio.sleep(0.01)
            assert server.stats.handler_errors == 1
            await client.ping(timeout=0.2)
    finally:
        await server.close()


async def test_server_handler_overload_sends_error_and_closes():
    release = asyncio.Event()

    async def handler(_peer: Peer, _frame: Frame) -> None:
        await release.wait()

    server = OpenNetServer(
        handler,
        host="127.0.0.1",
        port=0,
        max_handler_tasks=1,
    )
    await server.start()
    port = server.sockets[0].getsockname()[1]  # type: ignore[union-attr]
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    try:
        await write_frame(
            writer,
            Frame(
                FrameKind.DATA,
                topic="work/one",
                message_id=1,
                flags=Flags.ACK_REQUIRED,
            ),
            1024,
        )
        assert (await asyncio.wait_for(read_frame(reader), 1)).kind is FrameKind.ACK
        await write_frame(
            writer,
            Frame(FrameKind.DATA, topic="work/two", message_id=2),
            1024,
        )
        response = await asyncio.wait_for(read_frame(reader), 1)
        assert response.kind is FrameKind.ERROR
        assert response.payload == b"handler queue full"
        assert server.stats.overloaded_messages == 1
    finally:
        release.set()
        writer.close()
        await writer.wait_closed()
        await server.close()


@pytest.mark.parametrize("partial_frame", (b"", b"O"))
async def test_server_times_out_idle_or_partial_header(partial_frame):
    server = OpenNetServer(
        lambda _peer, _frame: None,
        host="127.0.0.1",
        port=0,
        idle_timeout=0.05,
        header_timeout=0.05,
    )
    await server.start()
    port = server.sockets[0].getsockname()[1]  # type: ignore[union-attr]
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    try:
        if partial_frame:
            writer.write(partial_frame)
            await writer.drain()
        assert await asyncio.wait_for(reader.read(), 1) == b""
        assert server.stats.timed_out_connections == 1
    finally:
        writer.close()
        await writer.wait_closed()
        await server.close()


async def test_server_times_out_partial_body():
    server = OpenNetServer(
        lambda _peer, _frame: None,
        host="127.0.0.1",
        port=0,
        body_timeout=0.05,
        min_body_bytes_per_second=1_000_000,
    )
    await server.start()
    port = server.sockets[0].getsockname()[1]  # type: ignore[union-attr]
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    encoded = Frame(
        FrameKind.DATA,
        ValueType.UTF8,
        topic="slow/body",
        payload=b"value",
        message_id=1,
    ).to_bytes()
    try:
        writer.write(encoded[:24])
        await writer.drain()
        assert await asyncio.wait_for(reader.read(), 1) == b""
        assert server.stats.timed_out_connections == 1
    finally:
        writer.close()
        await writer.wait_closed()
        await server.close()


async def test_authorizer_allows_before_handler_and_ack():
    events: list[str] = []

    async def authorizer(_peer: Peer, frame: Frame) -> bool:
        events.append(f"authorize:{frame.topic}")
        await asyncio.sleep(0)
        return frame.topic.startswith("allowed/")

    async def handler(_peer: Peer, frame: Frame) -> None:
        events.append(f"handle:{frame.topic}")

    server = OpenNetServer(
        handler,
        host="127.0.0.1",
        port=0,
        authorizer=authorizer,
    )
    await server.start()
    port = server.sockets[0].getsockname()[1]  # type: ignore[union-attr]
    try:
        async with OpenNetClient("127.0.0.1", port) as client:
            await client.send("allowed/temperature", 24.5)
        assert events == [
            "authorize:allowed/temperature",
            "handle:allowed/temperature",
        ]
        assert server.stats.authorization_denials == 0
    finally:
        await server.close()


async def test_authorizer_denial_sends_error_without_handler_or_ack():
    handled = False

    def authorizer(_peer: Peer, _frame: Frame) -> bool:
        return False

    async def handler(_peer: Peer, _frame: Frame) -> None:
        nonlocal handled
        handled = True

    server = OpenNetServer(
        handler,
        host="127.0.0.1",
        port=0,
        authorizer=authorizer,
    )
    await server.start()
    port = server.sockets[0].getsockname()[1]  # type: ignore[union-attr]
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    try:
        await write_frame(
            writer,
            Frame(
                FrameKind.DATA,
                topic="private/command",
                message_id=1,
                flags=Flags.ACK_REQUIRED,
            ),
            1024,
        )
        response = await asyncio.wait_for(read_frame(reader), 1)
        assert response.kind is FrameKind.ERROR
        assert response.payload == b"message not authorized"
        assert await asyncio.wait_for(reader.read(), 1) == b""
        assert not handled
        assert server.stats.authorization_denials == 1
    finally:
        writer.close()
        await writer.wait_closed()
        await server.close()


async def test_authorizer_exception_fails_closed():
    def authorizer(_peer: Peer, _frame: Frame) -> bool:
        raise RuntimeError("private policy detail")

    server = OpenNetServer(
        lambda _peer, _frame: pytest.fail("handler must not run"),
        host="127.0.0.1",
        port=0,
        authorizer=authorizer,
    )
    await server.start()
    port = server.sockets[0].getsockname()[1]  # type: ignore[union-attr]
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    try:
        await write_frame(
            writer,
            Frame(FrameKind.DATA, topic="private/command", message_id=1),
            1024,
        )
        response = await asyncio.wait_for(read_frame(reader), 1)
        assert response.kind is FrameKind.ERROR
        assert response.payload == b"message not authorized"
        assert b"policy" not in response.payload
        assert server.stats.authorization_denials == 1
    finally:
        writer.close()
        await writer.wait_closed()
        await server.close()


async def test_plaintext_peer_has_no_tls_certificate():
    observed: asyncio.Future[tuple[bool, object]] = (
        asyncio.get_running_loop().create_future()
    )

    def authorizer(peer: Peer, _frame: Frame) -> bool:
        observed.set_result((peer.tls_enabled, peer.tls_peer_certificate))
        return True

    server = OpenNetServer(
        lambda _peer, _frame: None,
        host="127.0.0.1",
        port=0,
        authorizer=authorizer,
    )
    await server.start()
    port = server.sockets[0].getsockname()[1]  # type: ignore[union-attr]
    try:
        async with OpenNetClient("127.0.0.1", port) as client:
            await client.send("public/status", "online")
        assert await asyncio.wait_for(observed, 1) == (False, None)
    finally:
        await server.close()


async def test_mutual_tls_certificate_can_authorize_a_topic():
    observed_common_names: list[str] = []

    def authorizer(peer: Peer, frame: Frame) -> bool:
        certificate = peer.tls_peer_certificate
        assert peer.tls_enabled
        assert certificate is not None
        subject = {
            key: value
            for relative_name in certificate["subject"]
            for key, value in relative_name
        }
        common_name = subject.get("commonName", "")
        observed_common_names.append(common_name)
        return common_name == "opennet-test-client" and frame.topic.startswith(
            "device/status"
        )

    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_context.load_cert_chain(CERTS / "server.crt", CERTS / "server.key")
    server_context.load_verify_locations(CERTS / "ca.crt")
    server_context.verify_mode = ssl.CERT_REQUIRED

    client_context = ssl.create_default_context(cafile=CERTS / "ca.crt")
    client_context.load_cert_chain(CERTS / "client.crt", CERTS / "client.key")

    server = OpenNetServer(
        lambda _peer, _frame: None,
        host="127.0.0.1",
        port=0,
        ssl_context=server_context,
        authorizer=authorizer,
    )
    await server.start()
    port = server.sockets[0].getsockname()[1]  # type: ignore[union-attr]
    try:
        async with OpenNetClient(
            "127.0.0.1",
            port,
            ssl_context=client_context,
        ) as client:
            await client.send("device/status", "online")
        assert observed_common_names == ["opennet-test-client"]
    finally:
        await server.close()
