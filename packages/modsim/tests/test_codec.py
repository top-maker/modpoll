"""Independent wire vectors and atomic property/Modbus write semantics."""

import asyncio
import json
from pathlib import Path

import pytest

from modsim.runtime import RuntimeContext
from modsim.utils import get_parser
from modsim.wot import configure

CONTEXT = [
    "https://www.w3.org/2022/wot/td/v1.1",
    {
        "modpoll": "https://top-maker.github.io/modpoll/vocab/wot-modbus#",
        "modv": "https://www.w3.org/2019/wot/modbus",
        "xsd": "http://www.w3.org/2001/XMLSchema#",
    },
]


def prop(
    raw="unsignedInt",
    quantity=2,
    kind="integer",
    address=0,
    entity="HoldingRegister",
    **extra,
):
    value = {
        "type": kind,
        "forms": [
            {
                "modv:entity": entity,
                "modv:address": address,
                "modv:quantity": quantity,
                "modv:type": "xsd:" + raw,
            }
        ],
    }
    if kind == "array":
        value["items"] = {"type": "boolean"}
    if entity in ("InputRegister", "DiscreteInput"):
        value["readOnly"] = True
    value.update(extra)
    return value


def configure_properties(tmp_path, properties, initial=None):
    groups = {}
    for name, value in properties.items():
        form = value["forms"][0]
        key = form["modv:entity"]
        groups.setdefault(key, []).append((name, form))
    acquisition = []
    for entity, forms in groups.items():
        start = min(form["modv:address"] for _, form in forms)
        end = max(form["modv:address"] + form["modv:quantity"] for _, form in forms)
        acquisition.append(
            {
                "modv:entity": entity,
                "modv:address": start,
                "modv:quantity": end - start,
                "modpoll:members": [name for name, _ in forms],
            }
        )
    document = {
        "@context": CONTEXT,
        "@type": "tm:ThingModel",
        "title": "codec-fixture",
        "modpoll:version": "0.2",
        "properties": properties,
        "modpoll:acquisition": acquisition,
    }
    path = tmp_path / "codec.tm.json"
    path.write_text(json.dumps(document))
    arguments = ["--config", str(path), "--unit-id", "1"]
    for name, value in (initial or {}).items():
        arguments.extend(["--initial", name + "=" + json.dumps(value)])
    args = get_parser().parse_args(arguments)
    configure(args)
    return args.runtime


@pytest.mark.parametrize(
    "order,words",
    [
        ("BE_BE", [0x1234, 0x5678]),
        ("LE_BE", [0x3412, 0x7856]),
        ("BE_LE", [0x5678, 0x1234]),
        ("LE_LE", [0x7856, 0x3412]),
    ],
)
def test_four_orders_independent_uint32_vector(tmp_path, order, words):
    mapping = prop()
    mapping["forms"][0].update(
        {
            "modv:mostSignificantByte": order.startswith("BE"),
            "modv:mostSignificantWord": order.endswith("BE"),
        }
    )
    instance = configure_properties(tmp_path, {"value": mapping}, {"value": 0x12345678})
    assert list(instance.cells["holding_register"].values()) == words
    assert instance.get("value") == 0x12345678


@pytest.mark.parametrize(
    "raw,quantity,kind,value,words",
    [
        ("short", 1, "integer", -12345, [0xCFC7]),
        ("int", 2, "integer", -12345678, [0xFF43, 0x9EB2]),
        (
            "unsignedLong",
            4,
            "integer",
            0x0123456789ABCDEF,
            [0x0123, 0x4567, 0x89AB, 0xCDEF],
        ),
        ("long", 4, "integer", -2, [0xFFFF, 0xFFFF, 0xFFFF, 0xFFFE]),
        ("float", 2, "number", -12.5, [0xC148, 0]),
        ("double", 4, "number", -12.5, [0xC029, 0, 0, 0]),
        ("boolean", 1, "boolean", True, [1]),
    ],
)
def test_numeric_wire_vectors(tmp_path, raw, quantity, kind, value, words):
    instance = configure_properties(
        tmp_path, {"value": prop(raw, quantity, kind)}, {"value": value}
    )
    assert list(instance.cells["holding_register"].values()) == words
    assert instance.get("value") == value


def test_float16_and_boolean_array_legacy_layout(tmp_path):
    half = prop("hexBinary", 1, "number")
    half["forms"][0]["modpoll:codec"] = "float16"
    instance = configure_properties(tmp_path, {"value": half}, {"value": 1.5})
    assert instance.cells["holding_register"][0] == 0x3E00
    for codec, quantity, values, expected in [
        ("bool8", 1, [True] + [False] * 6 + [True], [0x8100]),
        ("bool16", 2, [True] + [False] * 6 + [True, True] + [False] * 7, [0x8101, 0]),
    ]:
        mapping = prop("hexBinary", quantity, "array")
        mapping["forms"][0]["modpoll:codec"] = codec
        instance = configure_properties(tmp_path, {"value": mapping}, {"value": values})
        assert list(instance.cells["holding_register"].values()) == expected
        assert instance.get("value") == values


@pytest.mark.parametrize(
    "order,words",
    [
        ("BE_BE", [0xE4B8, 0xAD00]),
        ("LE_BE", [0xB8E4, 0x00AD]),
        ("BE_LE", [0xAD00, 0xE4B8]),
        ("LE_LE", [0x00AD, 0xB8E4]),
    ],
)
def test_utf8_odd_byte_capacity_and_order(tmp_path, order, words):
    mapping = prop("string", 2, "string")
    mapping["forms"][0].update(
        {
            "modpoll:byteLength": 3,
            "modv:mostSignificantByte": order.startswith("BE"),
            "modv:mostSignificantWord": order.endswith("BE"),
        }
    )
    instance = configure_properties(tmp_path, {"value": mapping}, {"value": "中"})
    assert list(instance.cells["holding_register"].values()) == words
    assert instance.get("value") == "中"
    with pytest.raises(ValueError):
        instance.set("value", "中文")
    assert instance.get("value") == "中"


def test_boolean_physical_array_and_legacy_msb_numeric_packing(tmp_path):
    array = prop("boolean", 5, "array", entity="Coil")
    values = [True, False, True, True, False]
    instance = configure_properties(tmp_path, {"value": array}, {"value": values})
    assert list(instance.cells["coil"].values()) == values
    assert instance.get("value") == values
    numeric = prop("unsignedShort", 16, "integer", entity="Coil")
    numeric["forms"][0]["modpoll:bitPacking"] = "legacy-msb"
    instance = configure_properties(tmp_path, {"value": numeric}, {"value": 0x1234})
    assert list(instance.cells["coil"].values()) == [
        bool(int(v)) for v in "0001001000110100"
    ]
    assert instance.get("value") == 0x1234


def test_exact_inverse_multiplier_negative_and_zero(tmp_path):
    mapping = prop("short", 1, "number")
    mapping["forms"][0]["modpoll:multiplier"] = -0.1
    instance = configure_properties(tmp_path, {"value": mapping}, {"value": 12.3})
    assert instance.cells["holding_register"][0] == 0xFF85
    assert instance.get("value") == 12.3
    with pytest.raises(ValueError, match="exact integer"):
        instance.set("value", 12.35)
    assert instance.get("value") == 12.3
    mapping["forms"][0]["modpoll:multiplier"] = 0
    instance = configure_properties(tmp_path, {"value": mapping})
    assert instance.get("value") == 0
    with pytest.raises(ValueError, match="zero multiplier"):
        instance.set("value", 1)


def test_uint64_initial_constraints_without_enumeration_or_float_loss(tmp_path):
    highest = (1 << 64) - 1
    mapping = prop(
        "unsignedLong", 4, "integer", minimum=highest - 2, maximum=highest, multipleOf=3
    )
    instance = configure_properties(tmp_path, {"value": mapping})
    assert instance.get("value") == highest
    assert list(instance.cells["holding_register"].values()) == [65535] * 4


def test_masks_preserve_neighbors_and_detect_alias_conflicts(tmp_path):
    flags = {}
    for name, bit in [("a", 0), ("b", 1)]:
        mapping = prop("unsignedShort", 1, "boolean")
        mapping["forms"][0]["modpoll:bit"] = bit
        flags[name] = mapping
    flags["word"] = prop("unsignedShort", 1)
    instance = configure_properties(tmp_path, flags, {"word": 0x8000})
    instance.set_many({"a": True, "b": True})
    assert instance.get("word") == 0x8003
    instance.set("a", False)
    assert instance.get("word") == 0x8002
    with pytest.raises(ValueError, match="alias"):
        instance.set_many({"word": 0, "b": True})
    assert instance.get("word") == 0x8002


def test_readonly_bits_and_writeonly_property(tmp_path):
    a = prop("unsignedShort", 1, "boolean", readOnly=True)
    a["forms"][0]["modpoll:bit"] = 0
    b = prop("unsignedShort", 1, "boolean")
    b["forms"][0]["modpoll:bit"] = 1
    instance = configure_properties(tmp_path, {"a": a, "b": b})
    context = RuntimeContext([instance])
    assert asyncio.run(context.async_setValues(1, 6, 0, [2])) is None
    assert asyncio.run(context.async_setValues(1, 6, 0, [3])) is not None
    assert instance.get("a") is False
    assert instance.get("b") is True
    instance = configure_properties(tmp_path, {"value": prop(writeOnly=True)})
    context = RuntimeContext([instance])
    assert not isinstance(asyncio.run(context.async_getValues(1, 3, 0, 2)), list)
    assert asyncio.run(context.async_setValues(1, 16, 0, [0x1234, 0x5678])) is None
    assert instance.get("value") == 0x12345678


def test_partial_float_write_validates_full_span_and_rolls_back(tmp_path):
    instance = configure_properties(
        tmp_path, {"value": prop("float", 2, "number", maximum=1.5)}, {"value": 1.5}
    )
    context = RuntimeContext([instance])
    assert asyncio.run(context.async_setValues(1, 6, 1, [1])) is not None
    assert instance.get("value") == 1.5
    assert asyncio.run(context.async_setValues(1, 6, 0, [0x3F80])) is None
    assert instance.get("value") == 1.0
    assert instance.held == {"value"}
    assert asyncio.run(context.async_setValues(1, 6, 0, [0x7F80])) is not None
    assert instance.get("value") == 1.0


def test_internal_alias_constraints_and_failed_batch_rollback(tmp_path):
    word = prop("unsignedShort", 1, maximum=1)
    bit = prop("unsignedShort", 1, "boolean")
    bit["forms"][0]["modpoll:bit"] = 1
    instance = configure_properties(tmp_path, {"word": word, "flag": bit})
    with pytest.raises(ValueError):
        instance.set("flag", True)
    assert instance.get("word") == 0


def test_legacy_bool16_full_span_write_preserves_padding(tmp_path):
    mapping = prop("hexBinary", 2, "array")
    mapping["forms"][0]["modpoll:codec"] = "bool16"
    instance = configure_properties(tmp_path, {"value": mapping})
    context = RuntimeContext([instance])
    assert asyncio.run(context.async_setValues(1, 16, 0, [0x8101, 0])) is None
    assert instance.get("value") == [True] + [False] * 6 + [True, True] + [False] * 7
    assert asyncio.run(context.async_setValues(1, 16, 0, [0, 1])) is not None
    assert instance.cells["holding_register"] == {0: 0x8101, 1: 0}


@pytest.mark.integration
def test_tcp_wide_values_partial_writes_and_writeonly(tmp_path):
    import os
    import socket
    import subprocess
    import sys
    import time
    from pymodbus.client import ModbusTcpClient

    properties = {
        "u32": prop(address=0),
        "u64": prop("unsignedLong", 4, address=2),
        "f32": prop("float", 2, "number", address=6, maximum=1.5),
        "f64": prop("double", 4, "number", address=8),
        "text": prop("string", 3, "string", address=12),
        "secret": prop("unsignedShort", 1, address=15, writeOnly=True),
        "flags": prop("boolean", 8, "array", entity="Coil"),
        "hidden_flag": prop(
            "boolean", 1, "boolean", entity="Coil", address=8, writeOnly=True
        ),
    }
    initial = {
        "u32": 0x12345678,
        "u64": 0x0123456789ABCDEF,
        "f32": 1.5,
        "f64": -12.5,
        "text": "abc",
        "secret": 7,
        "flags": [True, False] * 4,
    }
    configure_properties(tmp_path, properties, initial)
    initial_path = tmp_path / "initial.json"
    initial_path.write_text(json.dumps(initial))
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    root = Path(__file__).resolve().parents[1]
    client = ModbusTcpClient("127.0.0.1", port=port, timeout=0.5, retries=0)
    with (tmp_path / "server.log").open("w+") as log:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "modsim",
                "--config",
                str(tmp_path / "codec.tm.json"),
                "--initial-file",
                str(initial_path),
                "--port",
                str(port),
                "--unit-id",
                "1",
            ],
            cwd=tmp_path,
            env={**os.environ, "PYTHONPATH": str(root)},
            stdout=log,
            stderr=log,
        )
        try:
            deadline = time.monotonic() + 8
            while not client.connect():
                if process.poll() is not None or time.monotonic() > deadline:
                    log.seek(0)
                    pytest.fail(log.read())
                time.sleep(0.05)
            expected = [
                0x1234,
                0x5678,
                0x0123,
                0x4567,
                0x89AB,
                0xCDEF,
                0x3FC0,
                0,
                0xC029,
                0,
                0,
                0,
                0x6162,
                0x6300,
                0,
            ]
            assert (
                client.read_holding_registers(0, count=15, device_id=1).registers
                == expected
            )
            assert client.read_holding_registers(15, device_id=1).isError()
            assert not client.write_register(15, 9, device_id=1).isError()
            assert not client.write_coil(8, True, device_id=1).isError()
            assert client.read_coils(8, count=1, device_id=1).isError()
            assert (
                client.read_coils(0, count=8, device_id=1).bits[:8] == initial["flags"]
            )
            assert not client.write_coils(0, [False] * 8, device_id=1).isError()
            assert client.read_coils(0, count=8, device_id=1).bits[:8] == [False] * 8
            assert client.write_register(7, 1, device_id=1).isError()
            assert client.read_holding_registers(6, count=2, device_id=1).registers == [
                0x3FC0,
                0,
            ]
            assert not client.write_register(6, 0x3F80, device_id=1).isError()
            assert client.read_holding_registers(6, count=2, device_id=1).registers == [
                0x3F80,
                0,
            ]
            assert not client.write_registers(
                2, [0xFEDC, 0xBA98, 0x7654, 0x3210], device_id=1
            ).isError()
            assert client.read_holding_registers(2, count=4, device_id=1).registers == [
                0xFEDC,
                0xBA98,
                0x7654,
                0x3210,
            ]
            assert client.write_registers(12, [0xFFFF, 0, 0], device_id=1).isError()
            assert client.read_holding_registers(
                12, count=3, device_id=1
            ).registers == [0x6162, 0x6300, 0]
        finally:
            client.close()
            process.terminate()
            process.wait(timeout=5)
        assert process.returncode == 0


@pytest.mark.parametrize(
    "constraints", [{"exclusiveMinimum": 0}, {"exclusiveMaximum": 0}]
)
def test_float_initial_respects_exclusive_zero_bounds(tmp_path, constraints):
    instance = configure_properties(
        tmp_path, {"value": prop("float", 2, "number", **constraints)}
    )
    value = instance.get("value")
    assert value > 0 if "exclusiveMinimum" in constraints else value < 0


def test_float_rounding_reports_wire_value_and_rejects_unrepresentable_const(tmp_path):
    instance = configure_properties(
        tmp_path, {"value": prop("float", 2, "number")}, {"value": 0.1}
    )
    assert instance.cells["holding_register"] == {0: 0x3DCC, 1: 0xCCCD}
    assert instance.get("value") == 0.10000000149011612
    with pytest.raises(ValueError):
        configure_properties(tmp_path, {"value": prop("float", 2, "number", const=0.1)})


def test_impossible_string_length_is_rejected_without_large_allocation(tmp_path):
    with pytest.raises(ValueError):
        configure_properties(
            tmp_path, {"value": prop("string", 2, "string", minLength=10**9)}
        )


@pytest.mark.parametrize("raw,quantity", [("float", 2), ("double", 4)])
def test_float_initial_multipleof_intersects_declared_bounds(tmp_path, raw, quantity):
    instance = configure_properties(
        tmp_path,
        {
            "value": prop(
                raw, quantity, "number", minimum=100, maximum=200, multipleOf=7
            )
        },
    )
    assert instance.get("value") == 105
