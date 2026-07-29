import asyncio
import contextlib
import random

import pytest

from opennet import Flags, Frame, FrameKind, OpenNetClient, OpenNetServer, Peer, ValueType
from opennet.protocol import HEADER_SIZE, ProtocolError, inspect_header
from opennet.stream import read_frame

TRUNCATION_FRAME = Frame(
    FrameKind.DATA,
    ValueType.UTF8,
    "fault/topic",
    b"payload",
    message_id=17,
    flags=Flags.ACK_REQUIRED,
).to_bytes()


async def test_concurrent_sends_keep_frames_and_message_ids_distinct():
    received: asyncio.Queue[int] = asyncio.Queue()

    async def handler(_peer: Peer, frame: Frame) -> None:
        await received.put(frame.message_id)

    server = OpenNetServer(
        handler,
        host="127.0.0.1",
        port=0,
        max_handler_tasks=64,
    )
    await server.start()
    port = server.sockets[0].getsockname()[1]  # type: ignore[union-attr]
    try:
        async with OpenNetClient("127.0.0.1", port) as client:
            identifiers = await asyncio.gather(
                *(client.send(f"concurrent/{index}", index) for index in range(32))
            )
            delivered = [
                await asyncio.wait_for(received.get(), 1) for _ in identifiers
            ]
        assert identifiers == list(range(1, 33))
        assert sorted(delivered) == identifiers
    finally:
        await server.close()


@pytest.mark.parametrize("cut", range(len(TRUNCATION_FRAME)))
async def test_disconnect_at_every_frame_byte_is_rejected(cut: int):
    reader = asyncio.StreamReader()
    reader.feed_data(TRUNCATION_FRAME[:cut])
    reader.feed_eof()

    with pytest.raises(asyncio.IncompleteReadError):
        await read_frame(reader, max_payload=64)


async def test_complete_frame_after_all_truncation_points_still_decodes():
    reader = asyncio.StreamReader()
    reader.feed_data(TRUNCATION_FRAME)
    reader.feed_eof()
    assert await read_frame(reader, max_payload=64) == Frame(
        FrameKind.DATA,
        ValueType.UTF8,
        "fault/topic",
        b"payload",
        message_id=17,
        flags=Flags.ACK_REQUIRED,
    )


def test_deterministic_header_mutation_corpus_stays_bounded():
    valid_header = TRUNCATION_FRAME[:HEADER_SIZE]
    corpus: list[bytes] = []
    for byte_index in range(HEADER_SIZE):
        for bit_index in range(8):
            mutated = bytearray(valid_header)
            mutated[byte_index] ^= 1 << bit_index
            corpus.append(bytes(mutated))

    generator = random.Random(0x4F4E5031)
    corpus.extend(
        bytes(generator.getrandbits(8) for _ in range(HEADER_SIZE))
        for _ in range(2048)
    )

    for header in corpus:
        try:
            topic_length, payload_length = inspect_header(header, max_payload=64)
        except ProtocolError:
            continue
        assert 0 <= topic_length <= 1024
        assert 0 <= payload_length <= 64
        body = bytes(topic_length + payload_length)
        with contextlib.suppress(ProtocolError):
            Frame.from_parts(header, body, max_payload=64)


async def test_fragmented_ack_with_deterministic_delays_completes_send():
    async def accept(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        outbound = await read_frame(reader)
        encoded_ack = Frame(FrameKind.ACK, message_id=outbound.message_id).to_bytes()
        offset = 0
        for chunk_size in (1, 2, 3, 5, 8, 13):
            if offset >= len(encoded_ack):
                break
            writer.write(encoded_ack[offset : offset + chunk_size])
            await writer.drain()
            await asyncio.sleep(0)
            offset += chunk_size
        if offset < len(encoded_ack):
            writer.write(encoded_ack[offset:])
            await writer.drain()
        await read_frame(reader)
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(accept, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        async with OpenNetClient("127.0.0.1", port) as client:
            assert await client.send("fault/fragmented-ack", "ok") == 1
    finally:
        server.close()
        await server.wait_closed()
