"""Async stream helpers shared by client and server."""

from __future__ import annotations

import asyncio

from .protocol import DEFAULT_MAX_PAYLOAD, HEADER_SIZE, Frame, inspect_header


async def read_frame(
    reader: asyncio.StreamReader,
    max_payload: int = DEFAULT_MAX_PAYLOAD,
    *,
    idle_timeout: float | None = None,
    header_timeout: float | None = None,
    body_timeout: float | None = None,
    min_body_bytes_per_second: float | None = None,
) -> Frame:
    first = await asyncio.wait_for(reader.readexactly(1), timeout=idle_timeout)
    remainder = await asyncio.wait_for(
        reader.readexactly(HEADER_SIZE - 1),
        timeout=header_timeout,
    )
    header = first + remainder
    topic_length, payload_length = inspect_header(header, max_payload)
    body_length = topic_length + payload_length
    effective_body_timeout = body_timeout
    if (
        effective_body_timeout is not None
        and min_body_bytes_per_second is not None
        and body_length
    ):
        effective_body_timeout += body_length / min_body_bytes_per_second
    body = await asyncio.wait_for(
        reader.readexactly(body_length),
        timeout=effective_body_timeout,
    )
    return Frame.from_parts(header, body, max_payload)


async def write_frame(writer: asyncio.StreamWriter, frame: Frame, max_payload: int) -> None:
    writer.write(frame.to_bytes(max_payload))
    await writer.drain()
