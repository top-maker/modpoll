"""modpoll reads what modsim serves from the conformance model, over TCP and RTU (SIM-08)."""

import copy
import json
import struct

import modpoll_wot
from pymodbus.client import ModbusTcpClient
import pytest

from conftest import (
    DATA,
    FIXTURES,
    MODEL,
    ROOT,
    TRANSPORTS,
    endpoint_arguments,
    run_modpoll,
    simulator,
)

EXPECTED = json.loads(DATA.read_text())["initial"]


def words(raw):
    return [int.from_bytes(raw[i : i + 2], "big") for i in range(0, len(raw), 2)]


def swap_words(registers):
    return registers[::-1]


def swap_bytes(registers):
    return [((word & 0xFF) << 8) | (word >> 8) for word in registers]


# The holding registers modsim must put on the wire, worked out here from the Modbus byte and word
# order rules rather than by either tool's codec.
U32 = words(struct.pack(">I", EXPECTED["u32_be"]))
WIRE = {
    0: U32,
    2: swap_words(U32),
    4: swap_bytes(U32),
    6: swap_bytes(swap_words(U32)),
    8: swap_words(words(struct.pack(">f", EXPECTED["f32_word_swap"]))),
    10: words(struct.pack(">h", round(EXPECTED["i16_scaled"] / 0.1))),
    11: words(EXPECTED["label"].encode() + b"\0"),
    14: [1 << 3],
    15: words(struct.pack(">e", EXPECTED["half"])),
}


@pytest.mark.parametrize("transport", TRANSPORTS)
def test_every_point_reads_back_its_simulation_value(tmp_path, transport):
    with simulator(tmp_path, transport) as address:
        output = tmp_path / "values.json"
        result = run_modpoll(
            tmp_path,
            [
                *endpoint_arguments(transport, address),
                "--config",
                str(MODEL),
                "--export",
                str(output),
            ],
        )
        assert result.returncode == 0, result.stdout + result.stderr
    (values,) = json.loads(output.read_text()).values()
    assert values == EXPECTED


def test_modsim_puts_the_independently_encoded_registers_on_the_wire(tmp_path):
    with simulator(tmp_path, "tcp") as port:
        client = ModbusTcpClient("127.0.0.1", port=port, timeout=5)
        assert client.connect()
        try:
            reply = client.read_holding_registers(0, count=16, device_id=1)
        finally:
            client.close()
    assert not reply.isError()
    for address, expected in WIRE.items():
        assert reply.registers[address : address + len(expected)] == expected, address


@pytest.mark.parametrize("transport", TRANSPORTS)
def test_a_full_read_report_matches_its_model(tmp_path, transport):
    report_path = tmp_path / "report.json"
    with simulator(tmp_path, transport) as address:
        result = run_modpoll(
            tmp_path,
            [
                *endpoint_arguments(transport, address),
                "--config",
                str(MODEL),
                "--report",
                str(report_path),
            ],
        )
    assert report_path.is_file(), result.stdout + result.stderr
    report = json.loads(report_path.read_text())
    modpoll_wot.validate_report(report, model=MODEL.read_bytes())
    assert report["transport"] == transport
    assert {point["read"] for point in report["points"]} == {"ok"}
    assert len(report["points"]) == len(EXPECTED)


def test_an_address_the_device_does_not_serve_is_reported_as_exception_02(tmp_path):
    model = json.loads(MODEL.read_text())
    extended = copy.deepcopy(model)
    form = {**model["properties"]["u32_be"]["forms"][0], "modv:address": 100}
    extended["properties"]["unserved"] = {
        "type": "integer",
        "readOnly": True,
        "forms": [form],
    }
    extended["modpoll:acquisition"].append(
        {
            "modv:entity": "HoldingRegister",
            "modv:address": 100,
            "modv:quantity": 2,
            "modpoll:members": ["unserved"],
        }
    )
    client_model = tmp_path / "extended.tm.json"
    client_model.write_text(json.dumps(extended))
    report_path = tmp_path / "report.json"
    with simulator(tmp_path, "tcp") as port:
        result = run_modpoll(
            tmp_path,
            [
                *endpoint_arguments("tcp", port),
                "--config",
                str(client_model),
                "--report",
                str(report_path),
            ],
        )
    assert report_path.is_file(), result.stdout + result.stderr
    points = {
        point["property"]: point
        for point in json.loads(report_path.read_text())["points"]
    }
    assert (points["unserved"]["read"], points["unserved"].get("exceptionCode")) == (
        "exception",
        2,
    )
    assert {point["read"] for name, point in points.items() if name != "unserved"} == {
        "ok"
    }


def test_the_shared_fixture_has_no_drifting_copy():
    shared = (FIXTURES / "modsim.tm.json").read_bytes()
    assert (ROOT / "packages/modpoll/examples/modsim.tm.json").read_bytes() == shared
