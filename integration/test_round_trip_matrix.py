"""Read round trips over data type × byte and word order × multiplier × boundary value (CAT-09, WOT-07).

One generated model holds a point for every combination. Each boundary pass serves its values
with modsim and checks three readers against values worked out here with `struct`:

- the registers on the wire, read with pymodbus;
- modpoll's export;
- node-wot 0.9.2 reading the `node-wot-0.9.2` TD export, for the points that target supports
  (16- and 32-bit integers, 32- and 64-bit floats, no multiplier; WOT-07 step 2).

This replaces running every catalog product in modsim: the catalog only checks its Thing Models
statically, and encoding and decoding are covered once here.
"""

import json
import os
import shutil
import struct
import subprocess
from decimal import Decimal

import modpoll_wot
import pytest
from conftest import ROOT, endpoint_arguments, run_modpoll, simulator
from pymodbus.client import ModbusTcpClient

INTEROP = ROOT / "packages/modpoll/tools/wot-interop"

# Raw type: struct format, schema type, (lowest, highest) raw value or None for floats.
TYPES = {
    "xsd:unsignedShort": ("H", "integer", (0, 2**16 - 1)),
    "xsd:short": ("h", "integer", (-(2**15), 2**15 - 1)),
    "xsd:unsignedInt": ("I", "integer", (0, 2**32 - 1)),
    "xsd:int": ("i", "integer", (-(2**31), 2**31 - 1)),
    "xsd:unsignedLong": ("Q", "integer", (0, 2**64 - 1)),
    "xsd:long": ("q", "integer", (-(2**63), 2**63 - 1)),
    "xsd:float": ("f", "number", None),
    "xsd:double": ("d", "number", None),
}
ORDERS = [(True, True), (True, False), (False, True), (False, False)]
# Multipliers apply to integers up to 32 bits: a scaled 64-bit value is not exact as a float.
MULTIPLIERS = [None, "0.1", "-2"]
FLOAT_MAX = {
    "f": struct.unpack(">f", bytes.fromhex("7f7fffff"))[0],
    "d": struct.unpack(">d", bytes.fromhex("7fefffffffffffff"))[0],
}
FLOAT_TINY = {"f": struct.unpack(">f", bytes.fromhex("00000001"))[0], "d": 5e-324}
NODE_WOT = {"H", "h", "I", "i", "f", "d"}


def words(fmt, value, byte, word):
    """The registers that carry `value`, from the Modbus byte and word order rules."""
    data = struct.pack(">" + fmt, value)
    chunks = [data[i : i + 2] for i in range(0, len(data), 2)]
    if not word:
        chunks.reverse()
    if not byte:
        chunks = [chunk[::-1] for chunk in chunks]
    return [int.from_bytes(chunk, "big") for chunk in chunks]


def raw_passes(fmt, limits):
    """Lowest, highest, high bit set, and an asymmetric byte pattern."""
    if limits is None:
        biggest, tiny = FLOAT_MAX[fmt], FLOAT_TINY[fmt]
        return [-biggest, biggest, tiny, -1024.25]
    low, high = limits
    bits = struct.calcsize(fmt) * 8
    high_bit = 1 << (bits - 1) if low == 0 else -1
    pattern = int.from_bytes(bytes.fromhex("123456789abcdef0")[: bits // 8], "big")
    return [low, high, high_bit, pattern]


def points():
    """One point per combination, each in its own acquisition group."""
    address = 0
    for kind, (fmt, schema, limits) in TYPES.items():
        quantity = struct.calcsize(fmt) // 2
        orders = ORDERS if quantity > 1 else [(True, True), (False, True)]
        multipliers = MULTIPLIERS if limits and quantity <= 2 else [None]
        for byte, word in orders:
            for multiplier in multipliers:
                name = f"{kind[4:]}_{'b' if byte else 'l'}{'b' if word else 'l'}" + (
                    f"_x{multiplier.replace('-', 'm').replace('.', 'p')}"
                    if multiplier
                    else ""
                )
                yield {
                    "name": name,
                    "kind": kind,
                    "fmt": fmt,
                    "schema": schema,
                    "limits": limits,
                    "quantity": quantity,
                    "byte": byte,
                    "word": word,
                    "multiplier": multiplier,
                    "address": address,
                }
                address += quantity


POINTS = list(points())


def document(selected=POINTS):
    properties, groups = {}, []
    for point in selected:
        form = {
            "op": "readproperty",
            "contentType": "application/octet-stream",
            "modv:entity": "HoldingRegister",
            "modv:address": point["address"],
            "modv:quantity": point["quantity"],
            "modv:type": point["kind"],
            "modv:mostSignificantByte": point["byte"],
            "modv:mostSignificantWord": point["word"],
        }
        schema = point["schema"]
        if point["multiplier"]:
            form["modpoll:multiplier"] = point["multiplier"]
            schema = "number" if "." in point["multiplier"] else schema
        properties[point["name"]] = {"type": schema, "readOnly": True, "forms": [form]}
        groups.append(
            {
                "modv:entity": "HoldingRegister",
                "modv:address": point["address"],
                "modv:quantity": point["quantity"],
                "modpoll:members": [point["name"]],
            }
        )
    return {
        "@context": [
            "https://www.w3.org/2022/wot/td/v1.1",
            {
                "modpoll": "https://top-maker.github.io/modpoll/vocab/wot-modbus#",
                "modv": "https://www.w3.org/2019/wot/modbus",
                "xsd": "http://www.w3.org/2001/XMLSchema#",
            },
        ],
        "@type": "tm:ThingModel",
        "title": "round-trip-matrix",
        "modpoll:version": "0.2",
        "properties": properties,
        "modpoll:acquisition": groups,
    }


def engineering(point, raw):
    """The engineering value of a raw value: raw × multiplier as an exact decimal."""
    return (
        raw
        if point["multiplier"] is None
        else float(raw * Decimal(point["multiplier"]))
    )


def same(point, expected, actual):
    """Equal values; a 32-bit float is compared as the single-precision value it names."""
    if point["fmt"] == "f" and isinstance(actual, float):
        return struct.unpack(">f", struct.pack(">f", actual))[0] == expected
    return actual == expected and type(actual) is not bool


@pytest.fixture(scope="module")
def model(tmp_path_factory):
    path = tmp_path_factory.mktemp("matrix") / "matrix.tm.json"
    path.write_text(json.dumps(document()))
    modpoll_wot.load_model(path)  # the generated model is valid for the profile
    return path


def test_the_matrix_covers_every_combination():
    assert {(p["kind"], p["byte"], p["word"], p["multiplier"]) for p in POINTS} >= {
        (kind, byte, word, multiplier)
        for kind in ("xsd:unsignedInt", "xsd:int")
        for byte, word in ORDERS
        for multiplier in MULTIPLIERS
    }
    assert len({p["name"] for p in POINTS}) == len(POINTS)


@pytest.mark.parametrize(
    "boundary", range(4), ids=["lowest", "highest", "high-bit", "pattern"]
)
def test_every_reader_agrees_with_the_encoding_rules(tmp_path, model, boundary):
    raws = {p["name"]: raw_passes(p["fmt"], p["limits"])[boundary] for p in POINTS}
    expected = {p["name"]: engineering(p, raws[p["name"]]) for p in POINTS}
    data = tmp_path / "matrix.data.json"
    data.write_text(json.dumps({"version": "1", "initial": expected}))
    with simulator(tmp_path, "tcp", model=model, data=data) as port:
        wire = read_wire(port)
        values = read_modpoll(tmp_path, model, port)
        node = read_node_wot(tmp_path, port)

    for p in POINTS:
        assert wire[p["name"]] == words(
            p["fmt"], raws[p["name"]], p["byte"], p["word"]
        ), p["name"]
    mismatched = {
        p["name"]: (expected[p["name"]], values.get(p["name"]))
        for p in POINTS
        if not same(p, expected[p["name"]], values.get(p["name"]))
    }
    assert not mismatched, f"modpoll read (expected, actual): {mismatched}"
    if node is not None:
        assert node.keys() == {p["name"] for p in NODE_POINTS}
        mismatched = {
            p["name"]: (expected[p["name"]], node[p["name"]])
            for p in NODE_POINTS
            if not same(p, expected[p["name"]], node[p["name"]])
        }
        assert not mismatched, f"node-wot read (expected, actual): {mismatched}"


def read_wire(port):
    """Each point's registers, one request per point."""
    client = ModbusTcpClient("127.0.0.1", port=port, timeout=5)
    assert client.connect()
    try:
        wire = {}
        for p in POINTS:
            reply = client.read_holding_registers(
                p["address"], count=p["quantity"], device_id=1
            )
            assert not reply.isError(), (p["name"], reply)
            wire[p["name"]] = reply.registers
        return wire
    finally:
        client.close()


def read_modpoll(tmp_path, model, port):
    """modpoll's export, without the default pause between the requests of one poll."""
    output = tmp_path / "values.json"
    result = run_modpoll(
        tmp_path,
        [
            *endpoint_arguments("tcp", port),
            "--config",
            str(model),
            "--interval",
            "0",
            "--export",
            str(output),
        ],
    )
    assert result.returncode == 0, result.stdout + result.stderr
    (values,) = json.loads(output.read_text()).values()
    return values


NODE_POINTS = [p for p in POINTS if p["fmt"] in NODE_WOT and p["multiplier"] is None]


def read_node_wot(tmp_path, port):
    """node-wot's reads of the points its target supports, or None when it is not installed."""
    if not (INTEROP / "node_modules/@node-wot/core").exists():
        return None
    td = modpoll_wot.export_td(
        document(NODE_POINTS),
        host="127.0.0.1",
        port=port,
        unit_id=1,
        target="node-wot-0.9.2",
    )
    path = tmp_path / "matrix.td.json"
    path.write_text(json.dumps(td))
    result = subprocess.run(
        [shutil.which("node"), str(INTEROP / "read-write.cjs"), str(path)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    line = next(
        line for line in result.stdout.splitlines() if line.startswith("RESULT=")
    )
    return json.loads(line[len("RESULT=") :])


@pytest.mark.skipif(not os.environ.get("CI"), reason="node-wot is optional outside CI")
def test_node_wot_is_installed_in_ci():
    assert (INTEROP / "node_modules/@node-wot/core").exists(), (
        "npm ci --prefix packages/modpoll/tools/wot-interop"
    )
