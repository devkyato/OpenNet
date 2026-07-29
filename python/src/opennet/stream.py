"""Async stream helpers shared by client and server."""

from __future__ import annotations

import asyncio

from .protocol import DEFAULT_MAX_PAYLOAD, HEADER_SIZE, Frame, inspect_header


async def read_frame(
    reader: asyncio.StreamReader,
    max_payload: int = DEFAULT_MAX_PAYLOAD,
) -> Frame:
    header = await reader.readexactly(HEADER_SIZE)
    topic_length, payload_length = inspect_header(header, max_payload)
    body = await reader.readexactly(topic_length + payload_length)
    return Frame.from_parts(header, body, max_payload)


async def write_frame(writer: asyncio.StreamWriter, frame: Frame, max_payload: int) -> None:
    writer.write(frame.to_bytes(max_payload))
    await writer.drain()
