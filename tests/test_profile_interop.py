"""Wire and third-party Consumer acceptance for the 0.2 source candidate."""

import copy
import json
from pathlib import Path
import shutil
import struct
import subprocess
from unittest.mock import patch

import pytest
from pymodbus.client import ModbusTcpClient

profile = pytest.importorskip(
    "modpoll_wot.profile", reason="requires the candidate shared wheel/source"
)
from modpoll.modbus_task import ModbusHandler
from modpoll.wot_config import create_devices
from tools.verify_modsim_equivalence import assert_values

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[1]


def run_model(model, port):
    client = ModbusTcpClient("127.0.0.1", port=port)
    handler = ModbusHandler(client, "<contract-0.2>", interval=0, daemon=True)
    handler.deviceList = create_devices(model)
    handler.poll()
    device = handler.deviceList[0]
    assert device.pollSuccess
    return {name: ref.val for name, ref in device.references.items()}


def test_all_four_blocks_and_37_values_match_legacy(live_modsim):
    document = json.loads((ROOT / "examples/modsim.tm.json").read_text())
    model, td = profile.instantiate(document, host="127.0.0.1", port=live_modsim)
    reread, _ = profile.instantiate(td)
    for execution in (model, reread):
        assert_values({"modsim01": run_model(execution, live_modsim)})


def numeric_document():
    d = json.loads((ROOT / "tests/fixtures/numeric.tm.json").read_text())
    d["modpoll:version"] = "0.2"
    return d


def words(fmt, value, byte=True, word=True):
    data = struct.pack(">" + fmt, value)
    chunks = [data[i : i + 2] for i in range(0, len(data), 2)]
    if not word:
        chunks.reverse()
    if not byte:
        chunks = [part[::-1] for part in chunks]
    return [int.from_bytes(part, "big") for part in chunks]


def test_mixed_endian_transforms_bits_half_strings_remain_one_request(live_modsim):
    d = numeric_document()
    group = d["modpoll:acquisition"][0]
    group["modpoll:members"] = []
    d["properties"] = {}
    registers, expected = [], {}
    vectors = [
        ("unsigned", "xsd:unsignedShort", "integer", "H", 60000, True, True, {}),
        ("signed", "xsd:short", "integer", "h", -123, False, True, {}),
        ("long", "xsd:unsignedInt", "integer", "I", 0x89ABCDEF, True, False, {}),
        ("float", "xsd:float", "number", "f", -12.5, False, False, {}),
        ("double", "xsd:double", "number", "d", 1234.5, True, False, {}),
        (
            "half",
            "xsd:hexBinary",
            "number",
            "e",
            1.5,
            False,
            True,
            {"modpoll:codec": "float16"},
        ),
        (
            "scaled",
            "xsd:short",
            "number",
            "h",
            123,
            False,
            True,
            {"modpoll:multiplier": -0.1},
        ),
        (
            "zero",
            "xsd:short",
            "integer",
            "h",
            -123,
            True,
            True,
            {"modpoll:multiplier": 0},
        ),
        (
            "bit",
            "xsd:unsignedShort",
            "boolean",
            "H",
            0x8000,
            False,
            True,
            {"modpoll:bit": 15},
        ),
    ]
    for name, raw, schema, fmt, value, byte, word, extra in vectors:
        values = words(fmt, value, byte, word)
        form = {
            "op": "readproperty",
            "contentType": "application/octet-stream",
            "modv:entity": "HoldingRegister",
            "modv:address": 40000 + len(registers),
            "modv:quantity": len(values),
            "modv:type": raw,
            "modv:mostSignificantByte": byte,
            "modv:mostSignificantWord": word,
            **extra,
        }
        d["properties"][name] = {"type": schema, "readOnly": True, "forms": [form]}
        group["modpoll:members"].append(name)
        registers.extend(values)
        expected[name] = (
            True if name == "bit" else value * extra.get("modpoll:multiplier", 1)
        )
    alias = copy.deepcopy(d["properties"]["unsigned"])
    alias["type"] = "number"
    alias["forms"][0]["modpoll:multiplier"] = "0.1"
    d["properties"]["alias"] = alias
    group["modpoll:members"].append("alias")
    expected["alias"] = 6000.0
    group["modv:quantity"] = len(registers)
    client = ModbusTcpClient("127.0.0.1", port=live_modsim)
    try:
        assert client.connect()
        assert not client.write_registers(40000, registers, device_id=7).isError()
    finally:
        client.close()
    m, td = profile.instantiate(d, host="127.0.0.1", port=live_modsim, unit_id=7)
    assert len(m.groups) == 1
    for execution in (m, profile.instantiate(td)[0]):
        client = ModbusTcpClient("127.0.0.1", port=live_modsim)
        handler = ModbusHandler(client, "<mixed>", interval=0, daemon=True)
        handler.deviceList = create_devices(execution)
        with patch.object(
            client, "read_holding_registers", wraps=client.read_holding_registers
        ) as read:
            handler.poll()
            read.assert_called_once_with(40000, count=len(registers), device_id=7)
        assert {
            name: ref.val for name, ref in handler.deviceList[0].references.items()
        } == expected


def test_native_physical_bit_addresses_and_partial_arrays(live_modsim):
    d = numeric_document()
    d["properties"] = {}
    d["modpoll:acquisition"] = [
        {
            "modv:entity": "Coil",
            "modv:address": 0,
            "modv:quantity": 13,
            "modpoll:members": ["one", "tail"],
        }
    ]
    for name, address, count in (("one", 3, 1), ("tail", 9, 4)):
        p = {
            "type": "boolean" if count == 1 else "array",
            "readOnly": True,
            "forms": [
                {
                    "modv:entity": "Coil",
                    "modv:address": address,
                    "modv:quantity": count,
                    "modv:type": "xsd:boolean",
                    "op": "readproperty",
                }
            ],
        }
        if count > 1:
            p["items"] = {"type": "boolean"}
        d["properties"][name] = p
    client = ModbusTcpClient("127.0.0.1", port=live_modsim)
    try:
        assert client.connect()
        assert not client.write_coils(
            0,
            [
                False,
                False,
                False,
                True,
                False,
                False,
                False,
                False,
                False,
                True,
                False,
                True,
                True,
            ],
            device_id=7,
        ).isError()
    finally:
        client.close()
    model, td = profile.instantiate(d, host="127.0.0.1", port=live_modsim, unit_id=7)
    for execution in (model, profile.instantiate(td)[0]):
        assert run_model(execution, live_modsim) == {
            "one": True,
            "tail": [True, False, True, True],
        }


@pytest.mark.parametrize(
    "byte,word", [(True, True), (True, False), (False, True), (False, False)]
)
def test_actual_node_wot_reads_and_writes_exported_td(
    live_modsim, tmp_path, byte, word
):
    if not (ROOT / "tools/wot-interop/node_modules/@node-wot/core").exists():
        pytest.skip("run npm ci --prefix tools/wot-interop")
    d = numeric_document()
    for name, address, raw, schema, quantity in (
        ("large", 40008, "xsd:unsignedInt", "integer", 2),
        ("precise", 40010, "xsd:double", "number", 4),
    ):
        d["properties"][name] = {
            "type": schema,
            "readOnly": True,
            "forms": [
                {
                    "modv:entity": "HoldingRegister",
                    "modv:address": address,
                    "modv:quantity": quantity,
                    "modv:type": raw,
                    "op": "readproperty",
                }
            ],
        }
        d["modpoll:acquisition"][0]["modpoll:members"].append(name)
    d["modpoll:acquisition"][0]["modv:quantity"] = 14
    # Exercise unsigned values above signed range and independent byte/word orders.
    d["properties"]["counter"]["readOnly"] = False
    d["properties"]["counter"]["forms"][0]["op"] = ["readproperty", "writeproperty"]
    for prop in d["properties"].values():
        prop["forms"][0].update(
            {"modv:mostSignificantByte": byte, "modv:mostSignificantWord": word}
        )
    writes = {"counter": 50000}
    expected = {
        "counter": 50000,
        "signed": -123,
        "measurement": 12.5,
        "large": 3000000000,
        "precise": 1234.5,
    }
    if byte == word:
        writes.update(
            {
                "signed": -456,
                "measurement": 17.25,
                "large": 3000000123,
                "precise": 1234.75,
            }
        )
        expected.update(writes)
        for prop in d["properties"].values():
            prop["readOnly"] = False
            prop["forms"][0]["op"] = ["readproperty", "writeproperty"]
    client = ModbusTcpClient("127.0.0.1", port=live_modsim)
    try:
        assert client.connect()
        registers = (
            words("H", 60000, byte, word)
            + [999]
            + words("h", -123, byte, word)
            + [777]
            + words("f", 12.5, byte, word)
            + [555, 666]
            + words("I", 3000000000, byte, word)
            + words("d", 1234.5, byte, word)
        )
        assert not client.write_registers(40000, registers, device_id=7).isError()
    finally:
        client.close()
    td = profile.export_td(
        d, host="127.0.0.1", port=live_modsim, unit_id=7, target="node-wot-0.9.2"
    )
    path = tmp_path / "thing.json"
    path.write_text(json.dumps(td))
    node = shutil.which("node")
    assert node
    result = subprocess.run(
        [
            node,
            str(ROOT / "tools/wot-interop/read-write.cjs"),
            str(path),
            json.dumps(writes),
        ],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    line = next(
        line for line in result.stdout.splitlines() if line.startswith("RESULT=")
    )
    assert json.loads(line[7:]) == expected
    assert (
        run_model(
            profile.instantiate(d, host="127.0.0.1", port=live_modsim, unit_id=7)[0],
            live_modsim,
        )
        == expected
    )


@pytest.mark.parametrize(
    "byte,word", [(True, True), (True, False), (False, True), (False, False)]
)
def test_odd_utf8_string_respects_member_order(live_modsim, byte, word):
    d = numeric_document()
    d["properties"] = {
        "text": {
            "type": "string",
            "readOnly": True,
            "forms": [
                {
                    "modv:entity": "HoldingRegister",
                    "modv:address": 40000,
                    "modv:quantity": 2,
                    "modv:type": "xsd:string",
                    "modpoll:byteLength": 3,
                    "modv:mostSignificantByte": byte,
                    "modv:mostSignificantWord": word,
                }
            ],
        }
    }
    d["modpoll:acquisition"][0]["modpoll:members"] = ["text"]
    data = "水".encode() + b"\x00"
    chunks = [data[:2], data[2:]]
    if not word:
        chunks.reverse()
    if not byte:
        chunks = [part[::-1] for part in chunks]
    client = ModbusTcpClient("127.0.0.1", port=live_modsim)
    try:
        assert client.connect()
        assert not client.write_registers(
            40000, [int.from_bytes(part, "big") for part in chunks], device_id=7
        ).isError()
    finally:
        client.close()
    model, _ = profile.instantiate(d, unit_id=7)
    assert run_model(model, live_modsim) == {"text": "水"}


def test_explicit_legacy_packed_numeric_bits_at_physical_offset(live_modsim):
    d = numeric_document()
    d["properties"] = {
        "packed": {
            "type": "integer",
            "readOnly": True,
            "forms": [
                {
                    "modv:entity": "Coil",
                    "modv:address": 3,
                    "modv:quantity": 16,
                    "modv:type": "xsd:unsignedShort",
                    "modpoll:bitPacking": "legacy-msb",
                }
            ],
        }
    }
    d["modpoll:acquisition"] = [
        {
            "modv:entity": "Coil",
            "modv:address": 0,
            "modv:quantity": 20,
            "modpoll:members": ["packed"],
        }
    ]
    # Historical bit packing is explicit; no register codec is inferred from schema.
    bits = (
        [False] * 3
        + [
            bool(byte & (1 << (7 - index)))
            for byte in (0x12, 0x34)
            for index in range(8)
        ]
        + [False]
    )
    client = ModbusTcpClient("127.0.0.1", port=live_modsim)
    try:
        assert client.connect()
        assert not client.write_coils(0, bits, device_id=7).isError()
    finally:
        client.close()
    m, td = profile.instantiate(d, host="127.0.0.1", port=live_modsim, unit_id=7)
    for model in (m, profile.instantiate(td)[0]):
        assert run_model(model, live_modsim) == {"packed": 0x1234}


@pytest.mark.parametrize("entity,address", [("Coil", 3), ("HoldingRegister", 40000)])
def test_node_wot_native_scalar_boolean_read_write(
    live_modsim, tmp_path, entity, address
):
    if not (ROOT / "tools/wot-interop/node_modules/@node-wot/core").exists():
        pytest.skip("run npm ci --prefix tools/wot-interop")
    d = numeric_document()
    d["properties"] = {
        "switch": {
            "type": "boolean",
            "forms": [
                {
                    "modv:entity": entity,
                    "modv:address": address,
                    "modv:type": "xsd:boolean",
                }
            ],
        }
    }
    d["modpoll:acquisition"] = [
        {
            "modv:entity": entity,
            "modv:address": address,
            "modv:quantity": 1,
            "modpoll:members": ["switch"],
        }
    ]
    td = profile.export_td(
        d, host="127.0.0.1", port=live_modsim, unit_id=7, target="node-wot-0.9.2"
    )
    path = tmp_path / "boolean.json"
    path.write_text(json.dumps(td))
    result = subprocess.run(
        [
            shutil.which("node"),
            str(ROOT / "tools/wot-interop/read-write.cjs"),
            str(path),
            '{"switch":true}',
        ],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    line = next(
        line for line in result.stdout.splitlines() if line.startswith("RESULT=")
    )
    assert json.loads(line[7:]) == {"switch": True}
    assert run_model(profile.instantiate(d, unit_id=7)[0], live_modsim) == {
        "switch": True
    }


def test_app_uses_td_endpoint_without_transport_flags(live_modsim, tmp_path):
    client = ModbusTcpClient("127.0.0.1", port=live_modsim)
    try:
        assert client.connect()
        assert not client.write_registers(
            40000, [42, 0, 0xFF85, 0, 0x4148, 0, 0, 0], device_id=7
        ).isError()
    finally:
        client.close()
    from modpoll.arg_parser import get_parser
    from modpoll.modbus_task import setup_modbus_handlers

    td = profile.export_td(
        numeric_document(), host="127.0.0.1", port=live_modsim, unit_id=7
    )
    path = tmp_path / "no-extension"
    path.write_text(json.dumps(td))
    handlers = setup_modbus_handlers(
        get_parser().parse_args(["--config", str(path), "--daemon", "--interval", "0"])
    )
    try:
        assert len(handlers) == 1
        assert handlers[0].model.endpoint == ("127.0.0.1", live_modsim)
        handlers[0].poll()
        assert handlers[0].deviceList[0].pollSuccess
    finally:
        for handler in handlers:
            handler.close()


def test_app_cli_instantiates_typed_tm_parameters(live_modsim, tmp_path):
    import sys

    client = ModbusTcpClient("127.0.0.1", port=live_modsim)
    try:
        assert client.connect()
        assert not client.write_registers(
            40000, [42, 0, 0xFF85, 0, 0x4148, 0, 0, 0], device_id=7
        ).isError()
    finally:
        client.close()
    d = numeric_document()
    d["title"] = "meter-{{NAME}}"
    d["properties"]["counter"]["maximum"] = "{{LIMIT}}"
    path = tmp_path / "device.td.json"
    output = tmp_path / "values.json"
    path.write_text(json.dumps(d))
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "modpoll",
            "--config",
            str(path),
            "--tcp",
            "127.0.0.1",
            "--tcp-port",
            str(live_modsim),
            "--unit-id",
            "7",
            "--param",
            'NAME="one"',
            "--param",
            "LIMIT=100",
            "--once",
            "--daemon",
            "--interval",
            "0",
            "--export",
            str(output),
        ],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert json.loads(output.read_text()) == {
        "meter-one": {"counter": 42, "signed": -123, "measurement": 12.5}
    }
