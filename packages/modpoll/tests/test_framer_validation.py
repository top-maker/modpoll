import pytest

from modpoll.arg_parser import get_parser
from modpoll import modbus_task as mt


def _fake_args(argv):
    parser = get_parser()
    return parser.parse_args(argv)


def test_rtu_with_ascii_framer_supported(monkeypatch):
    captured = {}

    def fake_serial_client(**kwargs):
        captured.update(kwargs)
        return "serial-client"

    monkeypatch.setattr(mt, "ModbusSerialClient", fake_serial_client)

    args = _fake_args(
        [
            "--config",
            "dummy.tm.json",
            "--serial",
            "/dev/ttyUSB0",
            "--framer",
            "ascii",
        ]
    )

    mt._create_modbus_client(args)

    assert captured["framer"] is mt.FramerType.ASCII


def test_tcp_with_ascii_framer_rejected():
    args = _fake_args(
        [
            "--config",
            "dummy.tm.json",
            "--tcp",
            "localhost",
            "--framer",
            "ascii",
        ]
    )

    with pytest.raises(ValueError):
        mt._create_modbus_client(args)


def test_multiple_transports_rejected():
    args = _fake_args(
        [
            "--config",
            "dummy.tm.json",
            "--serial",
            "/dev/ttyUSB0",
            "--tcp",
            "localhost",
        ]
    )

    with pytest.raises(ValueError):
        mt._create_modbus_client(args)


def test_tcp_socket_framer_is_applied(monkeypatch):
    captured = {}

    def fake_tcp_client(**kwargs):
        captured.update(kwargs)
        return "tcp-client"

    monkeypatch.setattr(mt, "ModbusTcpClient", fake_tcp_client)

    args = _fake_args(
        [
            "--config",
            "dummy.tm.json",
            "--tcp",
            "localhost",
            "--framer",
            "socket",
        ]
    )

    client = mt._create_modbus_client(args)

    assert client == "tcp-client"
    assert captured["framer"] is mt.FramerType.SOCKET


def test_rtu_alias_still_parses(monkeypatch):
    captured = {}

    def fake_serial_client(**kwargs):
        captured.update(kwargs)
        return "serial-client"

    monkeypatch.setattr(mt, "ModbusSerialClient", fake_serial_client)

    args = _fake_args(
        [
            "--config",
            "dummy.tm.json",
            "--rtu",
            "/dev/ttyUSB0",
            "--framer",
            "rtu",
        ]
    )

    client = mt._create_modbus_client(args)

    assert client == "serial-client"
    assert captured["port"] == "/dev/ttyUSB0"


@pytest.mark.parametrize(
    "transport,framer",
    [("serial", "rtu"), ("serial", "ascii"), ("tcp", "socket"), ("udp", "socket")],
)
def test_explicit_framer_constructs_real_pymodbus_client(transport, framer):
    endpoint = "loop://" if transport == "serial" else "localhost"
    args = _fake_args(
        ["--config", "unused.tm.json", "--" + transport, endpoint, "--framer", framer]
    )
    client = mt._create_modbus_client(args)
    assert client is not None
    client.close()
