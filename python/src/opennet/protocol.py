"""ONP/1 framing and typed-value codec."""

from __future__ import annotations

import json
import math
import struct
import zlib
from dataclasses import dataclass
from enum import IntEnum, IntFlag
from typing import Any, Final, Tuple

MAGIC: Final = b"ON"
VERSION: Final = 1
HEADER: Final = struct.Struct("!2sBBBBHIIII")
HEADER_SIZE: Final = HEADER.size
MAX_TOPIC_SIZE: Final = 1024
DEFAULT_MAX_PAYLOAD: Final = 16 * 1024 * 1024


class ProtocolError(ValueError):
    """Raised when bytes violate ONP/1."""


class DeliveryTimeout(TimeoutError):
    """Raised when an acknowledged DATA frame exhausts its retry budget."""

    def __init__(self, message_id: int, attempts: int) -> None:
        self.message_id = message_id
        self.attempts = attempts
        super().__init__(
            f"message {message_id} was not acknowledged after {attempts} attempt(s)"
        )


class FrameKind(IntEnum):
    DATA = 1
    ACK = 2
    PING = 3
    PONG = 4
    CLOSE = 5
    ERROR = 6


class Flags(IntFlag):
    NONE = 0
    ACK_REQUIRED = 1
    DUPLICATE = 2


class ValueType(IntEnum):
    BYTES = 0
    UTF8 = 1
    JSON = 2
    INT64 = 3
    FLOAT64 = 4
    BOOL = 5
    NULL = 6


@dataclass(frozen=True)
class Frame:
    kind: FrameKind
    value_type: ValueType = ValueType.NULL
    topic: str = ""
    payload: bytes = b""
    message_id: int = 0
    flags: Flags = Flags.NONE

    def __post_init__(self) -> None:
        topic_bytes = self.topic.encode("utf-8")
        if len(topic_bytes) > MAX_TOPIC_SIZE:
            raise ProtocolError("topic is longer than 1024 UTF-8 bytes")
        if self.kind is FrameKind.DATA:
            if not topic_bytes:
                raise ProtocolError("DATA frames require a topic")
            if not 1 <= self.message_id <= 0xFFFFFFFF:
                raise ProtocolError("DATA message_id must be between 1 and 2^32-1")
        elif self.topic:
            raise ProtocolError("control frames must not contain a topic")
        if self.kind is FrameKind.ACK:
            if not 1 <= self.message_id <= 0xFFFFFFFF:
                raise ProtocolError("ACK message_id must be between 1 and 2^32-1")
            if self.payload or self.value_type is not ValueType.NULL:
                raise ProtocolError("ACK frames must have an empty NULL payload")
        elif self.kind in (FrameKind.PING, FrameKind.PONG):
            if self.message_id != 0 or self.payload or self.value_type is not ValueType.NULL:
                raise ProtocolError("PING and PONG frames must be empty")
        elif self.kind in (FrameKind.CLOSE, FrameKind.ERROR):
            if self.message_id != 0:
                raise ProtocolError("CLOSE and ERROR message_id must be zero")
            if self.payload and self.value_type is not ValueType.UTF8:
                raise ProtocolError("CLOSE and ERROR payloads must be UTF-8")
        if not 0 <= self.message_id <= 0xFFFFFFFF:
            raise ProtocolError("message_id is outside uint32 range")
        if int(self.flags) & ~int(Flags.ACK_REQUIRED | Flags.DUPLICATE):
            raise ProtocolError("reserved flag bits are set")

    def to_bytes(self, max_payload: int = DEFAULT_MAX_PAYLOAD) -> bytes:
        topic = self.topic.encode("utf-8")
        if len(self.payload) > max_payload:
            raise ProtocolError(f"payload exceeds configured {max_payload}-byte limit")
        checksum = zlib.crc32(topic)
        checksum = zlib.crc32(self.payload, checksum) & 0xFFFFFFFF
        return b"".join(
            (
                HEADER.pack(
                    MAGIC,
                    VERSION,
                    int(self.kind),
                    int(self.flags),
                    int(self.value_type),
                    len(topic),
                    self.message_id,
                    len(self.payload),
                    checksum,
                    0,
                ),
                topic,
                self.payload,
            )
        )

    @classmethod
    def from_parts(
        cls,
        header: bytes,
        body: bytes,
        max_payload: int = DEFAULT_MAX_PAYLOAD,
    ) -> "Frame":
        if len(header) != HEADER_SIZE:
            raise ProtocolError(f"header must be exactly {HEADER_SIZE} bytes")
        (
            magic,
            version,
            raw_kind,
            raw_flags,
            raw_type,
            topic_length,
            message_id,
            payload_length,
            expected_crc,
            _reserved,
        ) = HEADER.unpack(header)
        if magic != MAGIC:
            raise ProtocolError("invalid frame magic")
        if version != VERSION:
            raise ProtocolError(f"unsupported protocol version {version}")
        if raw_flags & ~int(Flags.ACK_REQUIRED | Flags.DUPLICATE):
            raise ProtocolError("reserved flag bits are set")
        if topic_length > MAX_TOPIC_SIZE:
            raise ProtocolError("topic exceeds protocol limit")
        if payload_length > max_payload:
            raise ProtocolError("payload exceeds configured limit")
        if len(body) != topic_length + payload_length:
            raise ProtocolError("body length does not match header")
        topic_bytes = body[:topic_length]
        payload = body[topic_length:]
        checksum = zlib.crc32(topic_bytes)
        checksum = zlib.crc32(payload, checksum) & 0xFFFFFFFF
        if checksum != expected_crc:
            raise ProtocolError("CRC-32 mismatch")
        try:
            topic = topic_bytes.decode("utf-8")
            kind = FrameKind(raw_kind)
            value_type = ValueType(raw_type)
        except (UnicodeDecodeError, ValueError) as exc:
            raise ProtocolError(str(exc)) from exc
        frame = cls(kind, value_type, topic, payload, message_id, Flags(raw_flags))
        if kind is FrameKind.DATA:
            decode_value(value_type, payload)
        return frame


def inspect_header(header: bytes, max_payload: int = DEFAULT_MAX_PAYLOAD) -> Tuple[int, int]:
    """Validate allocation-sensitive header fields and return body lengths."""
    if len(header) != HEADER_SIZE:
        raise ProtocolError(f"header must be exactly {HEADER_SIZE} bytes")
    (
        magic,
        version,
        _kind,
        flags,
        _type,
        topic_length,
        _message_id,
        payload_length,
        _crc,
        _reserved,
    ) = HEADER.unpack(header)
    if magic != MAGIC or version != VERSION:
        raise ProtocolError("invalid magic or unsupported version")
    if flags & ~int(Flags.ACK_REQUIRED | Flags.DUPLICATE):
        raise ProtocolError("reserved flag bits are set")
    if topic_length > MAX_TOPIC_SIZE or payload_length > max_payload:
        raise ProtocolError("declared frame size exceeds configured limit")
    return topic_length, payload_length


def encode_value(value: Any, value_type: ValueType | None = None) -> tuple[ValueType, bytes]:
    """Encode a Python value, inferring the ONP type when omitted."""
    if value_type is None:
        if value is None:
            value_type = ValueType.NULL
        elif isinstance(value, bool):
            value_type = ValueType.BOOL
        elif isinstance(value, bytes):
            value_type = ValueType.BYTES
        elif isinstance(value, str):
            value_type = ValueType.UTF8
        elif isinstance(value, int):
            value_type = ValueType.INT64
        elif isinstance(value, float):
            value_type = ValueType.FLOAT64
        else:
            value_type = ValueType.JSON

    if value_type is ValueType.NULL:
        if value is not None:
            raise TypeError("NULL requires None")
        return value_type, b""
    if value_type is ValueType.BOOL:
        if not isinstance(value, bool):
            raise TypeError("BOOL requires bool")
        return value_type, bytes((int(value),))
    if value_type is ValueType.BYTES:
        if not isinstance(value, bytes):
            raise TypeError("BYTES requires bytes")
        return value_type, value
    if value_type is ValueType.UTF8:
        if not isinstance(value, str):
            raise TypeError("UTF8 requires str")
        return value_type, value.encode("utf-8")
    if value_type is ValueType.JSON:
        return value_type, json.dumps(
            value, ensure_ascii=False, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    if value_type is ValueType.INT64:
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError("INT64 requires int")
        try:
            return value_type, struct.pack("!q", value)
        except struct.error as exc:
            raise OverflowError("integer is outside int64 range") from exc
    if value_type is ValueType.FLOAT64:
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise TypeError("FLOAT64 requires a number")
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("FLOAT64 must be finite")
        return value_type, struct.pack("!d", number)
    raise TypeError(f"unsupported value type {value_type!r}")


def decode_value(value_type: ValueType, payload: bytes) -> Any:
    """Decode and strictly validate an ONP typed payload."""
    try:
        if value_type is ValueType.NULL:
            if payload:
                raise ProtocolError("NULL payload must be empty")
            return None
        if value_type is ValueType.BOOL:
            if payload not in (b"\x00", b"\x01"):
                raise ProtocolError("BOOL payload must be one 0 or 1 byte")
            return payload == b"\x01"
        if value_type is ValueType.BYTES:
            return payload
        if value_type is ValueType.UTF8:
            return payload.decode("utf-8")
        if value_type is ValueType.JSON:
            return json.loads(payload.decode("utf-8"))
        if value_type is ValueType.INT64:
            if len(payload) != 8:
                raise ProtocolError("INT64 payload must be 8 bytes")
            return struct.unpack("!q", payload)[0]
        if value_type is ValueType.FLOAT64:
            if len(payload) != 8:
                raise ProtocolError("FLOAT64 payload must be 8 bytes")
            value = struct.unpack("!d", payload)[0]
            if not math.isfinite(value):
                raise ProtocolError("FLOAT64 must be finite")
            return value
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProtocolError(str(exc)) from exc
    raise ProtocolError(f"unsupported value type {value_type!r}")
