from modpoll.modbus_task import Device, Poller, Point


class FakeResult:
    def __init__(self, *, bits=None, registers=None):
        self.bits = bits
        self.registers = registers

    def isError(self):
        return False


def test_poller_uses_discrete_inputs_for_fc2():
    device = Device("dev", 1)
    poller = Poller(device, 2, 0, 2, "BE_BE")
    point = Point(device, "di0", "0", "bool", "r", None, None)
    poller.add_readable_point(point)

    class FakeMaster:
        def __init__(self):
            self.called = None

        def read_discrete_inputs(self, start_address, *, count, device_id=None):
            self.called = ("di", start_address, count)
            return FakeResult(bits=[1, 0])

        def read_coils(self, *args, **kwargs):  # pragma: no cover - should not be used
            raise AssertionError("read_coils should not be called for fc=2")

    master = FakeMaster()

    assert poller.poll(master) is True
    assert master.called == ("di", 0, 2)
    # Value decoding path should have set a value for the reference
    assert point.val is not None


def test_bit_point_decodes_multiple_bits_same_register():
    device = Device("dev", 1)
    poller = Poller(device, 4, 40000, 1, "BE_BE")
    point_msb = Point(device, "bit15", "40000:15", "bool", "r", None, None)
    point_lsb = Point(device, "bit0", "40000:0", "bool", "r", None, None)
    poller.add_readable_point(point_msb)
    poller.add_readable_point(point_lsb)

    class FakeMaster:
        def __init__(self):
            self.called = None

        def read_input_registers(self, start_address, *, count, device_id=None):
            self.called = ("ir", start_address, count)
            return FakeResult(registers=[0x8001])  # 1000 0000 0000 0001

    master = FakeMaster()

    assert poller.poll(master) is True
    assert master.called == ("ir", 40000, 1)
    assert point_msb.val is True
    assert point_lsb.val is True


def test_bit_point_respects_endianness():
    device = Device("dev", 1)
    poller = Poller(device, 4, 0, 1, "LE_BE")
    point_bit15 = Point(device, "bit15", "0:15", "bool", "r", None, None)
    point_bit7 = Point(device, "bit7", "0:7", "bool", "r", None, None)
    poller.add_readable_point(point_bit15)
    poller.add_readable_point(point_bit7)

    class FakeMaster:
        def __init__(self):
            self.called = None

        def read_input_registers(self, start_address, *, count, device_id=None):
            self.called = ("ir", start_address, count)
            return FakeResult(registers=[0x8001])  # raw register value

    master = FakeMaster()

    assert poller.poll(master) is True
    assert master.called == ("ir", 0, 1)
    # LE byte order swaps bytes: 0x8001 -> 0x0180 (bit7 set, bit15 clear)
    assert point_bit15.val is False
    assert point_bit7.val is True


def test_bit_syntax_only_allowed_with_bool_dtype():
    import pytest

    device = Device("dev", 1)

    # Should work: bool dtype with bit syntax
    point_bool = Point(device, "bit_ref", "40000:5", "bool", "r", None, None)
    assert point_bool.bit == 5

    # Should fail: uint16 dtype with bit syntax
    with pytest.raises(ValueError, match="can only be used with dtype 'bool'"):
        Point(device, "uint_ref", "40000:5", "uint16", "r", None, None)

    # Should fail: int32 dtype with bit syntax
    with pytest.raises(ValueError, match="can only be used with dtype 'bool'"):
        Point(device, "int_ref", "40000:0", "int32", "r", None, None)

    # Should work: uint16 dtype without bit syntax
    point_uint = Point(device, "uint_ref", "40000", "uint16", "r", None, None)
    assert point_uint.bit is None


def test_coil_groups_decode_independently_in_any_point_order():
    device = Device("dev", 1)
    poller = Poller(device, 1, 100, 16, "BE_BE")
    second = Point(device, "second", "101", "bool8", "r", None, None)
    first = Point(device, "first", "100", "bool8", "r", None, None)
    poller.add_readable_point(second)
    poller.add_readable_point(first)
    bits = [
        True,
        False,
        False,
        True,
        False,
        False,
        True,
        False,
        False,
        True,
        True,
        False,
        True,
        False,
        False,
        True,
    ]

    class Client:
        def read_coils(self, address, count, device_id):
            return FakeResult(bits=bits)

    assert poller.poll(Client())
    assert first.val == bits[:8]
    assert second.val == bits[8:]


def test_coil_group_reports_only_requested_bits_and_rejects_short_response():
    device = Device("dev", 1)
    poller = Poller(device, 1, 0, 10, "BE_BE")
    point = Point(device, "tail", "1", "bool8", "r", None, None)
    poller.add_readable_point(point)

    class Client:
        bits = [True, False] * 8

        def read_coils(self, address, count, device_id):
            return FakeResult(bits=self.bits)

    client = Client()
    assert poller.poll(client)
    assert point.val == [True, False]
    client.bits = [True] * 9
    assert not poller.poll(client)
    assert not point.valid_this_poll
