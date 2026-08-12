import argparse

import pytest

from opennet.cli import (
    _frame_log_fields,
    _require_secure_remote,
    _topic_prefix_authorizer,
    _value_from_args,
    build_parser,
)
from opennet.protocol import Frame, FrameKind, ValueType


@pytest.mark.parametrize(
    ("kind", "text", "expected"),
    [
        ("text", "hello", "hello"),
        ("json", '{"ok":true}', {"ok": True}),
        ("int", "-42", -42),
        ("float", "3.25", 3.25),
        ("bool", "false", False),
        ("null", None, None),
        ("hex", "00 ff", b"\x00\xff"),
    ],
)
def test_cli_value_conversion(kind, text, expected):
    args = argparse.Namespace(type=kind, value=text)
    assert _value_from_args(args) == expected


def test_cli_has_operational_subcommands():
    parser = build_parser()
    for command in ("serve", "send", "ping", "benchmark", "doctor"):
        with pytest.raises(SystemExit) as result:
            parser.parse_args((command, "--help"))
        assert result.value.code == 0


def test_send_keeps_topic_and_value_as_the_only_positionals():
    args = build_parser().parse_args(["send", "sensor/temperature", "24.7"])
    assert args.host == "127.0.0.1"
    assert args.topic == "sensor/temperature"
    assert args.value == "24.7"


def test_plaintext_remote_requires_explicit_opt_in():
    _require_secure_remote("127.0.0.1", tls=False, allow_plaintext=False)
    _require_secure_remote("192.168.1.20", tls=True, allow_plaintext=False)
    with pytest.raises(ValueError, match="plaintext"):
        _require_secure_remote("192.168.1.20", tls=False, allow_plaintext=False)


def test_oversized_file_is_rejected_before_read(tmp_path, monkeypatch):
    path = tmp_path / "payload.bin"
    path.write_bytes(b"four")

    def fail_if_read(_path):
        raise AssertionError("oversized file should not be read")

    monkeypatch.setattr(type(path), "read_bytes", fail_if_read)
    args = argparse.Namespace(type="file", value=str(path), max_payload=3)
    with pytest.raises(ValueError, match="4 bytes"):
        _value_from_args(args)


def test_server_logs_metadata_without_values_by_default():
    frame = Frame(
        FrameKind.DATA,
        ValueType.UTF8,
        "secret/topic",
        b"token",
        message_id=1,
    )
    fields = _frame_log_fields(frame, include_value=False)
    assert fields == {
        "id": frame.message_id,
        "topic": "secret/topic",
        "value_type": "utf8",
        "payload_bytes": 5,
    }
    assert _frame_log_fields(frame, include_value=True)["value"] == "token"


def test_cli_topic_prefix_policy_is_explicit():
    policy = _topic_prefix_authorizer(("sensor/", "status/"))
    assert policy is not None
    allowed = Frame(
        FrameKind.DATA,
        ValueType.INT64,
        "sensor/temperature",
        (24).to_bytes(8, "big", signed=True),
        message_id=1,
    )
    denied = Frame(
        FrameKind.DATA,
        ValueType.BOOL,
        "admin/reset",
        b"\x01",
        message_id=2,
    )
    assert policy(None, allowed)  # type: ignore[arg-type]
    assert not policy(None, denied)  # type: ignore[arg-type]
    assert _topic_prefix_authorizer(()) is None
    with pytest.raises(ValueError, match="cannot be empty"):
        _topic_prefix_authorizer(("",))


def test_serve_value_logging_is_opt_in():
    args = build_parser().parse_args(["serve", "--allow-topic-prefix", "sensor/"])
    assert args.log_values is False
    assert args.allow_topic_prefix == ["sensor/"]
    assert args.max_payload > 0
