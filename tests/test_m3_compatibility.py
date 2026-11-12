"""Regression cases for legitimate v1 mappings and precise v2 failure reporting."""

import json

import pytest

from modpoll.modbus_task import Device, Poller, Point, ModbusHandler
from modpoll.wot_config import create_devices
from modpoll_wot import AcquisitionError, parse_model
from tests.wot_helpers import meter_model, raw_form


class Result:
    def __init__(self, registers=None, bits=None):
        self.registers, self.bits = registers, bits

    def isError(self):
        return False


@pytest.mark.parametrize("entity", ["Coil", "DiscreteInput"])
@pytest.mark.parametrize("count", [16, 17])
def test_numeric_bit_tables_decode_complete_bytes(entity, count):
    document = meter_model("bits", start=0, count=count)
    group = document["modpoll:acquisition"][0]
    group["modv:entity"] = entity
    form = raw_form("uint16", 0, quantity=16, entity=entity)
    form["modpoll:bitPacking"] = "legacy-msb"
    document["properties"]["value"]["forms"] = [form]

    # Legacy fromCoils numeric decoding reverses bit order within each byte.
    class Client:
        def read_coils(self, *args, **kwargs):
            return Result(
                bits=[True, False, True, False, False, False, False, True] * 2
                + [False] * (count - 16)
            )

        read_discrete_inputs = read_coils

    (device,) = create_devices(parse_model(document))
    (poller,) = device.pollerList
    assert poller.poll(Client())
    assert device.points["value"].val == 0xA1A1
    group["modv:quantity"] = 15
    with pytest.raises(AcquisitionError, match="outside group"):
        parse_model(document)


def test_bit_table_string_span_counts_bytes_not_registers():
    document = meter_model("bits", count=24)
    document["properties"]["value"]["type"] = "string"
    group = document["modpoll:acquisition"][0]
    group["modv:entity"] = "Coil"
    form = raw_form("string3", 0, quantity=24, entity="Coil")
    form["modpoll:bitPacking"] = "legacy-msb"
    document["properties"]["value"]["forms"] = [form]
    (device,) = create_devices(parse_model(document))

    class Client:
        def read_coils(self, *args, **kwargs):
            return Result(
                bits=[bool(byte & (1 << (7 - i))) for byte in b"ABC" for i in range(8)]
            )

    assert device.pollerList[0].poll(Client())
    assert device.points["value"].val == "ABC"
    group["modv:quantity"] = 23
    with pytest.raises(AcquisitionError, match="outside group"):
        parse_model(document)


def test_aliases_decode_every_property_from_one_read():
    document = meter_model()
    document["properties"]["signed"] = {
        "type": "integer",
        "readOnly": True,
        "forms": [raw_form("int16", 0)],
    }
    document["modpoll:acquisition"][0]["modpoll:members"].append("signed")
    (device,) = create_devices(parse_model(document))

    class Client:
        calls = 0

        def read_holding_registers(self, *args, **kwargs):
            self.calls += 1
            return Result(registers=[65535])

    client = Client()
    assert device.pollerList[0].poll(client)
    assert client.calls == 1
    assert {n: r.val for n, r in device.points.items()} == {
        "value": 65535,
        "signed": -1,
    }


@pytest.mark.parametrize("dtype", ["bool8", "bool16", "uint16", "string1"])
def test_empty_register_response_is_invalid(dtype):
    device = Device("meter", 1)
    point = Point(device, "value", "0", dtype, "r", None, None)
    poller = Poller(device, 3, 0, 2, "BE_BE")
    poller.add_readable_point(point)

    class Client:
        def read_holding_registers(self, *args, **kwargs):
            return Result(registers=[])

    assert not poller.poll(Client())
    assert not point.valid_this_poll and point.val is None


@pytest.mark.parametrize("exception", [False, True])
def test_failed_attempts_update_diagnostic_counts(exception):
    class Client:
        def connect(self):
            return exception

        def close(self):
            pass

        def read_holding_registers(self, *args, **kwargs):
            raise OSError("link lost")

    device = Device("meter", 1)
    poller = Poller(device, 3, 0, 1, "BE_BE")
    point = Point(device, "value", "0", "uint16", "r", None, None)
    poller.add_readable_point(point)
    device.add_point_mapping(point)
    device.pollerList = [poller]
    handler = ModbusHandler(
        Client(), "test.tm.json", daemon=True, autoremove=True, interval=0
    )
    handler.deviceList = [device]
    for count in (1, 2, 3):
        handler.poll()
        assert (device.pollCount, device.errorCount) == (count, count)
        assert not device.pollSuccess
    assert poller.disabled
    handler.poll()
    assert (device.pollCount, device.errorCount) == (3, 3)


def test_write_only_property_stays_out_of_decoded_output():
    document = meter_model()
    document["properties"]["write_value"] = {
        "type": "integer",
        "writeOnly": True,
        "forms": [raw_form("uint16", 1)],
    }
    document["modpoll:acquisition"][0]["modv:quantity"] = 2
    document["modpoll:acquisition"][0]["modpoll:members"].append("write_value")
    (device,) = create_devices(parse_model(document))

    class Client:
        def read_holding_registers(self, *args, **kwargs):
            return Result(registers=[42, 99])

    assert device.pollerList[0].poll(Client())
    assert device.points["value"].val == 42
    assert not device.points["write_value"].valid_this_poll
    assert [point.name for point in device.pollerList[0].readablePoints] == ["value"]


def test_poll_count_is_per_cycle_not_per_poller():
    class Client:
        failing = {2}

        def connect(self):
            return True

        def close(self):
            pass

        def read_holding_registers(self, address, *args, **kwargs):
            if address in self.failing:
                raise OSError("link lost")
            return Result(registers=[1])

    client = Client()
    device = Device("meter", 1)
    for address in range(3):
        poller = Poller(device, 3, address, 1, "BE_BE")
        point = Point(device, f"value{address}", str(address), "uint16", "r", None, None)
        poller.add_readable_point(point)
        device.pollerList.append(poller)
    handler = ModbusHandler(
        client, "test.tm.json", daemon=True, autoremove=False, interval=0
    )
    handler.deviceList = [device]
    handler.poll()
    handler.poll()
    assert (device.pollCount, device.errorCount, device.pollSuccess) == (2, 2, False)
    client.failing = set()
    handler.poll()
    assert (device.pollCount, device.errorCount, device.pollSuccess) == (3, 2, True)
