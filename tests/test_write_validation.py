"""Write requests are validated before any I/O, and failures are reported as False."""

import logging

import pytest
from pymodbus.exceptions import ModbusException

from modpoll.modbus_task import Device, ModbusHandler, Point, Poller, _get_parity


class Response:
    def __init__(self, error=False):
        self.error = error

    def isError(self):
        return self.error


class Client:
    def __init__(self, *, connects=True, error=False, raises=None):
        self.connects, self.error, self.raises = connects, error, raises
        self.calls = []

    def connect(self):
        return self.connects

    def close(self):
        pass

    def _write(self, kind, *args, **kwargs):
        self.calls.append((kind, *args))
        if self.raises:
            raise self.raises
        return Response(self.error)

    def write_coil(self, *args, **kwargs):
        return self._write("coil", *args)

    def write_register(self, *args, **kwargs):
        return self._write("register", *args)

    def write_registers(self, *args, **kwargs):
        return self._write("registers", *args)


def handler_for(client):
    handler = ModbusHandler(client, "unused.tm.json")
    handler.deviceList = [Device("meter", 7)]
    return handler


@pytest.mark.parametrize(
    "address, value",
    [(-1, 1), (65536, 1), (0, 2), (0, "1"), (0, 1.0), (0, None), (0, [1])],
)
def test_invalid_coil_writes_never_reach_the_client(address, value):
    client = Client()
    assert not handler_for(client).write_coil("meter", address, value)
    assert client.calls == []


def test_coil_write_failures_are_reported_not_raised(caplog):
    caplog.set_level(logging.ERROR)
    assert not handler_for(Client(connects=False)).write_coil("meter", 1, True)
    assert not handler_for(Client(error=True)).write_coil("meter", 1, True)
    assert not handler_for(Client(raises=OSError("down"))).write_coil("meter", 1, True)
    assert not handler_for(Client()).write_coil("missing", 1, True)
    assert "Device missing not found" in caplog.text
    assert "Error writing coil: down" in caplog.text


def test_register_span_limit_is_123_values_and_the_address_space_end():
    client = Client()
    handler = handler_for(client)
    assert handler.write_register("meter", 0, [1] * 123)
    assert not handler.write_register("meter", 0, [1] * 124)
    assert handler.write_register("meter", 65536 - 123, [1] * 123)
    assert not handler.write_register("meter", 65536 - 122, [1] * 123)
    assert [call[0] for call in client.calls] == ["registers", "registers"]


@pytest.mark.parametrize(
    "value", [-1, 65536, True, 1.5, "7", None, [True], [-1], [65536]]
)
def test_invalid_register_values_are_rejected_without_io(value):
    client = Client()
    assert not handler_for(client).write_register("meter", 0, value)
    assert client.calls == []


def test_register_write_failures_are_reported_not_raised(caplog):
    caplog.set_level(logging.ERROR)
    assert not handler_for(Client(connects=False)).write_register("meter", 1, 5)
    assert not handler_for(Client(error=True)).write_register("meter", 1, 5)
    failing = Client(raises=ModbusException("illegal"))
    assert not handler_for(failing).write_register("meter", 1, [1, 2])
    assert "Error writing register: " in caplog.text


def test_modbus_exception_while_reading_fails_the_poll_without_raising(caplog):
    class Reader:
        def read_holding_registers(self, *args, **kwargs):
            raise ModbusException("no response")

    device = Device("meter", 1)
    poller = Poller(device, 3, 0, 1, "BE_BE")
    poller.add_readable_point(Point(device, "v", "0", "uint16", "r", None, None))
    with caplog.at_level(logging.ERROR):
        assert not poller.poll(Reader())
    assert "Modbus exception: meter 3 0 1" in caplog.text
    assert poller.failcounter == 1 and not device.pollSuccess


@pytest.mark.parametrize(
    "name, expected", [("odd", "O"), ("even", "E"), ("none", "N"), (None, "N")]
)
def test_serial_parity_maps_to_pymodbus_codes(name, expected):
    assert _get_parity(name) == expected
