import argparse

import pytest

from opennet.cli import _require_secure_remote, _value_from_args, build_parser


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
    for command in ("serve", "send", "ping", "benchmark"):
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
