from modpoll.modbus_task import Device, ModbusHandler


class FakeClient:
    def __init__(self):
        self.calls = []

    def connect(self):
        return True

    def close(self):
        pass

    def write_coil(self, address, value, *, device_id):
        self.calls.append(("write_coil", address, value, device_id))
        return FakeResponse()

    def write_register(self, address, value, *, device_id):
        self.calls.append(("write_register", address, value, device_id))
        return FakeResponse()

    def write_registers(self, address, values, *, device_id):
        self.calls.append(("write_registers", address, values, device_id))
        return FakeResponse()


class FakeResponse:
    def isError(self):
        return False


def make_handler():
    client = FakeClient()
    handler = ModbusHandler(client, "unused.tm.json")
    handler.deviceList = [Device("meter", 7)]
    return handler, client


def test_single_writes_use_locked_pymodbus_device_id_keyword():
    handler, client = make_handler()

    assert handler.write_coil("meter", 12, True)
    assert handler.write_register("meter", 13, 456)
    assert client.calls == [
        ("write_coil", 12, True, 7),
        ("write_register", 13, 456, 7),
    ]


def test_documented_multiple_register_write_uses_fc16_and_same_unit():
    handler, client = make_handler()

    assert handler.write_register("meter", 40001, [12, 13, 14, 15])
    assert client.calls == [("write_registers", 40001, [12, 13, 14, 15], 7)]


def test_invalid_register_write_is_rejected_without_io():
    handler, client = make_handler()

    assert not handler.write_register("meter", 40001, [])
    assert not handler.write_register("meter", 40001, [1, -1])
    assert not handler.write_register("meter", 40001, [1, 65536])
    assert client.calls == []
