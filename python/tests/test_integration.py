import asyncio
import ssl
from pathlib import Path

import pytest

from opennet import Flags, Frame, FrameKind, OpenNetClient, OpenNetServer, Peer, decode_value
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
