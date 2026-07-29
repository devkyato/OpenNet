import struct

import pytest

from opennet.protocol import (
    HEADER,
    Flags,
    Frame,
    FrameKind,
    ProtocolError,
    ValueType,
    decode_value,
    encode_value,
    inspect_header,
)


@pytest.mark.parametrize(
    ("value", "expected_type"),
    [
        (None, ValueType.NULL),
        (True, ValueType.BOOL),
        (b"\x00\xff", ValueType.BYTES),
        ("hello", ValueType.UTF8),
        (42, ValueType.INT64),
        (3.5, ValueType.FLOAT64),
        ({"ok": True}, ValueType.JSON),
    ],
)
def test_typed_value_round_trip(value, expected_type):
    value_type, payload = encode_value(value)
    assert value_type is expected_type
    assert decode_value(value_type, payload) == value


def test_frame_round_trip_and_known_vector():
    value_type, payload = encode_value({"celsius": 24.5}, ValueType.JSON)
    frame = Frame(
        FrameKind.DATA,
        value_type,
        "sensor/temp",
        payload,
        0x01020304,
        Flags.ACK_REQUIRED,
    )
    encoded = frame.to_bytes()
    # Fixed vector consumed by implementations in other languages.
    assert encoded.hex() == (
        "4f4e01010102000b010203040000001049a1dc1c00000000"
        "73656e736f722f74656d707b2263656c73697573223a32342e357d"
    )
    topic_length, payload_length = inspect_header(encoded[: HEADER.size])
    decoded = Frame.from_parts(
        encoded[: HEADER.size],
        encoded[HEADER.size : HEADER.size + topic_length + payload_length],
    )
    assert decoded == frame


def test_bad_crc_is_rejected():
    encoded = bytearray(
        Frame(FrameKind.DATA, ValueType.UTF8, "topic", b"value", 1).to_bytes()
    )
    encoded[-1] ^= 0x01
    with pytest.raises(ProtocolError, match="CRC"):
        Frame.from_parts(bytes(encoded[: HEADER.size]), bytes(encoded[HEADER.size :]))


def test_oversize_is_rejected_before_body_allocation():
    header = HEADER.pack(
        b"ON",
        1,
        FrameKind.DATA,
        0,
        ValueType.BYTES,
        1,
        1,
        4097,
        0,
        0,
    )
    with pytest.raises(ProtocolError, match="size"):
        inspect_header(header, max_payload=4096)


@pytest.mark.parametrize(
    ("value_type", "payload"),
    [
        (ValueType.BOOL, b"\x02"),
        (ValueType.INT64, b"\x00"),
        (ValueType.FLOAT64, struct.pack("!d", float("nan"))),
        (ValueType.NULL, b"x"),
    ],
)
def test_invalid_typed_payloads(value_type, payload):
    with pytest.raises(ProtocolError):
        decode_value(value_type, payload)
