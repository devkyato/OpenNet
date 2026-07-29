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
    "frame",
    [
        Frame(FrameKind.ACK, message_id=1),
        Frame(FrameKind.PING),
        Frame(FrameKind.PONG),
        Frame(FrameKind.CLOSE),
        Frame(FrameKind.ERROR),
    ],
)
def test_control_frames_round_trip(frame):
    encoded = frame.to_bytes()
    decoded = Frame.from_parts(encoded[: HEADER.size], encoded[HEADER.size :])
    assert decoded == frame


@pytest.mark.parametrize(
    "factory",
    [
        lambda: Frame(FrameKind.ACK),
        lambda: Frame(FrameKind.ACK, payload=b"x", message_id=1),
        lambda: Frame(FrameKind.PING, message_id=1),
        lambda: Frame(FrameKind.PONG, topic="not-allowed"),
        lambda: Frame(FrameKind.ERROR, payload=b"not-null"),
    ],
)
def test_invalid_control_frames_are_rejected(factory):
    with pytest.raises(ProtocolError):
        factory()


def test_nonzero_reserved_header_is_ignored_for_forward_compatibility():
    encoded = bytearray(Frame(FrameKind.PING).to_bytes())
    encoded[20:24] = b"\x01\x02\x03\x04"
    assert inspect_header(bytes(encoded[: HEADER.size])) == (0, 0)
    assert (
        Frame.from_parts(bytes(encoded[: HEADER.size]), b"").kind is FrameKind.PING
    )


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


def test_received_data_payload_must_match_declared_type():
    encoded = bytearray(
        Frame(
            FrameKind.DATA,
            ValueType.BYTES,
            "sensor/value",
            b"\x02",
            7,
        ).to_bytes()
    )
    encoded[5] = int(ValueType.BOOL)
    with pytest.raises(ProtocolError, match="BOOL"):
        Frame.from_parts(bytes(encoded[: HEADER.size]), bytes(encoded[HEADER.size :]))


@pytest.mark.parametrize("constant", (b"NaN", b"Infinity", b"-Infinity"))
def test_json_rejects_non_standard_numeric_constants(constant):
    with pytest.raises(ProtocolError, match="non-standard JSON"):
        decode_value(ValueType.JSON, constant)
