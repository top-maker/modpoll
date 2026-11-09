"""M2 read-path acceptance against independently encoded Modbus data."""

import copy
from functools import partial
import http.server
import json
from pathlib import Path
import struct
import subprocess
import sys
import threading

import pytest
from pymodbus.client import ModbusTcpClient

from modpoll.arg_parser import get_parser
from modpoll.modbus_task import setup_modbus_handlers
from tests.wot_helpers import meter_model, raw_form

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[1]


def wire_registers(format_, value, byte_big, word_big):
    # Encode independently of the shared interpreter and PyModbus payload codec.
    data = struct.pack(">" + format_, value)
    words = [data[i : i + 2] for i in range(0, len(data), 2)]
    if not word_big:
        words.reverse()
    if not byte_big:
        words = [word[::-1] for word in words]
    return [int.from_bytes(word, "big") for word in words]


@pytest.mark.parametrize(
    "byte_big,word_big", [(True, True), (True, False), (False, True), (False, False)]
)
def test_all_numeric_types_bits_strings_and_multipliers(
    live_modsim, tmp_path, byte_big, word_big
):
    document = meter_model("vectors")
    document["properties"] = {}
    group = document["modpoll:acquisition"][0]
    group.update(
        {
            "modv:address": 40000,
            "modpoll:members": [],
        }
    )
    registers, expected = [], {}

    def add(name, dtype, values, value, type_="number", multiplier=None, bit=None):
        offset = len(registers)
        registers.extend(values)
        form = raw_form(
            dtype, group["modv:address"] + offset, quantity=len(values), bit=bit
        )
        form.update(
            {"modv:mostSignificantByte": byte_big, "modv:mostSignificantWord": word_big}
        )
        if dtype.startswith("string"):
            form.update(
                {"modv:mostSignificantByte": True, "modv:mostSignificantWord": True}
            )
        if multiplier is not None:
            form["modpoll:multiplier"] = multiplier
        document["properties"][name] = {
            "type": type_,
            "readOnly": True,
            "unit": "test",
            "forms": [form],
        }
        group["modpoll:members"].append(name)
        expected[name] = value

    cases = [
        ("half", "float16", "e", 1.5),
        ("signed16", "int16", "h", -1234),
        ("unsigned16", "uint16", "H", 65530),
        ("signed32", "int32", "i", -2000000001),
        ("unsigned32", "uint32", "I", 4000000000),
        ("signed64", "int64", "q", -(2**61) + 17),
        ("unsigned64", "uint64", "Q", 0xFEDCBA9876543210),
        ("float32", "float32", "f", 3.125),
        ("float64", "float64", "d", -123.5),
    ]
    for name, dtype, format_, value in cases:
        add(name, dtype, wire_registers(format_, value, byte_big, word_big), value)
    # The existing string codec reads byte sequences without numeric endian swaps.
    add("label", "string3", [0x4142, 0x4358], "ABC", type_="string")
    for name, factor, result in [
        ("zero", "0", 0.0),
        ("negative", "-0.5", 617.0),
        ("fractional", "0.001", -1.234),
    ]:
        add(
            name,
            "int16",
            wire_registers("h", -1234, byte_big, word_big),
            result,
            multiplier=factor,
        )
    add(
        "bit0",
        "bool",
        wire_registers("H", 0x8001, byte_big, word_big),
        True,
        type_="boolean",
        bit=0,
    )
    # A second bit view references the same raw register, with a distinct bit selector.
    document["properties"]["bit15"] = copy.deepcopy(document["properties"]["bit0"])
    document["properties"]["bit15"].pop("unit", None)
    document["properties"]["bit15"]["forms"][0]["modpoll:bit"] = 15
    group["modpoll:members"].append("bit15")
    expected["bit15"] = True
    group["modv:quantity"] = len(registers)
    config = tmp_path / "vectors.tm.json"
    config.write_text(json.dumps(document))
    client = ModbusTcpClient("127.0.0.1", port=live_modsim)
    try:
        assert client.connect()
        assert not client.write_registers(40000, registers, device_id=7).isError()
    finally:
        client.close()
    args = get_parser().parse_args(
        [
            "--tcp",
            "127.0.0.1",
            "--tcp-port",
            str(live_modsim),
            "--config",
            str(config),
            "--unit-id",
            "7",
            "--daemon",
            "--interval",
            "0",
        ]
    )
    handlers = setup_modbus_handlers(args)
    try:
        (handler,) = handlers
        handler.poll()
        (device,) = handler.deviceList
        assert device.pollSuccess
        actual = {name: point.val for name, point in device.points.items()}
        assert actual == expected
        assert type(actual["unsigned64"]) is int
        assert type(actual["signed64"]) is int
        output = tmp_path / "snapshot.json"
        assert handler.export(output)
        assert json.loads(output.read_text()) == {"vectors": expected}

        class Capture:
            messages = []

            def publish(self, topic, payload):
                self.messages.append((topic, json.loads(payload)))

        capture = Capture()
        handler.mqtt_handler = capture
        handler.mqtt_publish_topic_pattern = "test/{{device_name}}/data"
        handler.publish_data()
        topic, payload = capture.messages[-1]
        assert topic == "test/vectors/data"
        assert payload["half|test"] == 1.5
        assert payload["signed64|test"] == -(2**61) + 17
        assert payload["label|test"] == "ABC"
        assert payload["negative|test"] == 617.0
        assert payload["bit15"] is True

    finally:
        for handler in handlers:
            handler.close()


class QuietHttpHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@pytest.mark.parametrize("kind", ["tm", "td"])
def test_url_and_local_multi_device_cli_json_and_timestamp(live_modsim, tmp_path, kind):
    source_name = "modsim.tm.json" if kind == "tm" else "modsim.generated.td.json"
    source = json.loads((ROOT / "examples" / source_name).read_text())
    source["title"] = "http-device"
    (tmp_path / f"meter.{kind}.json").write_text(json.dumps(source))
    source["title"] = "local-device"
    local = tmp_path / f"local.{kind}.json"
    local.write_text(json.dumps(source))
    server = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0), partial(QuietHttpHandler, directory=str(tmp_path))
    )
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    output = tmp_path / "output.json"
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}/meter.{kind}.json"
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "modpoll",
                "--once",
                "--tcp",
                "127.0.0.1",
                "--tcp-port",
                str(live_modsim),
                "--config",
                url,
                str(local),
                "--export",
                str(output),
                "--timestamp",
                "--interval",
                "0",
                "--delay",
                "0",
                "--loglevel",
                "ERROR",
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=15,
        )
        assert result.returncode == 0, result.stderr
        assert not result.stderr.strip(), result.stderr
        data = json.loads(output.read_text())
        assert set(data) == {"http-device", "local-device"}
        assert data["http-device"] == data["local-device"]
        assert len(data["http-device"]) == 38
        assert isinstance(data["http-device"]["timestamp"], (int, float))
        assert data["http-device"]["holding_reg15"] == 12345678900
        assert data["http-device"]["holding_reg19"] == "this is a string"
        assert data["http-device"]["input_reg10"] == 12345.678
    finally:
        server.shutdown()
        worker.join(timeout=5)
        server.server_close()


def test_device_exception_produces_null_without_hiding_valid_group(
    live_modsim, tmp_path
):
    document = meter_model("partial", start=40000)
    group = copy.deepcopy(document["modpoll:acquisition"][0])
    group["modv:address"] = 50000  # In Modbus range, outside the simulator datastore.
    group["modpoll:members"] = ["unavailable"]
    document["properties"]["unavailable"] = {
        "type": "integer",
        "readOnly": True,
        "forms": [raw_form("uint16", 50000)],
    }
    document["modpoll:acquisition"].append(group)
    config = tmp_path / "partial.tm.json"
    config.write_text(json.dumps(document))
    args = get_parser().parse_args(
        [
            "--tcp",
            "127.0.0.1",
            "--tcp-port",
            str(live_modsim),
            "--config",
            str(config),
            "--daemon",
            "--interval",
            "0",
        ]
    )
    handlers = setup_modbus_handlers(args)
    try:
        (handler,) = handlers
        handler.poll()
        (device,) = handler.deviceList
        assert not device.pollSuccess
        assert device.points["value"].valid_this_poll
        assert not device.points["unavailable"].valid_this_poll
        output = tmp_path / "partial.json"
        assert handler.export(output)
        assert json.loads(output.read_text()) == {
            "partial": {"value": 1, "unavailable": None}
        }
    finally:
        for handler in handlers:
            handler.close()


@pytest.mark.parametrize("remote", [False, True], ids=["local-file", "http-url"])
def test_invalid_point_fails_entire_configuration_before_network_poll(tmp_path, remote):
    document = meter_model()
    document["properties"]["bad"] = {
        "type": "integer",
        "readOnly": True,
        "forms": [raw_form("uint64", 1)],
    }
    document["modpoll:acquisition"][0]["modpoll:members"].append("bad")
    path = tmp_path / "invalid.tm.json"
    path.write_text(json.dumps(document))
    server = None
    if remote:
        server = http.server.ThreadingHTTPServer(
            ("127.0.0.1", 0), partial(QuietHttpHandler, directory=str(tmp_path))
        )
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        location = f"http://127.0.0.1:{server.server_address[1]}/{path.name}"
    else:
        location = str(path)
    output = tmp_path / "must-not-exist.json"
    try:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "modpoll",
                "--once",
                "--tcp",
                "127.0.0.1",
                "--tcp-port",
                "1",
                "--config",
                location,
                "--export",
                str(output),
                "--loglevel",
                "ERROR",
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=10,
        )
        assert result.returncode != 0
        assert "member outside group" in result.stderr
        assert "invalid.tm.json" in result.stderr
        assert not output.exists()
    finally:
        if server is not None:
            server.shutdown()
            worker.join(timeout=5)
            server.server_close()


def test_multiple_models_send_their_own_unit_ids(live_modsim, tmp_path):
    from tools.verify_modsim_equivalence import Proxy, Handler

    first = meter_model("first", start=40000)
    second = meter_model("second", start=40000)
    first["properties"]["value"]["forms"][0]["modv:unitID"] = 2
    second["properties"]["value"]["forms"][0]["modv:unitID"] = 7
    paths = [tmp_path / "first.tm.json", tmp_path / "second.tm.json"]
    for path, model in zip(paths, (first, second)):
        path.write_text(json.dumps(model))
    output = tmp_path / "multi-unit.json"
    with Proxy(("127.0.0.1", 0), Handler) as proxy:
        proxy.upstream, proxy.requests, proxy.errors = (
            ("127.0.0.1", live_modsim),
            [],
            [],
        )
        thread = threading.Thread(target=proxy.serve_forever, daemon=True)
        thread.start()
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "modpoll",
                    "--once",
                    "--tcp",
                    "127.0.0.1",
                    "--tcp-port",
                    str(proxy.server_address[1]),
                    "--config",
                    *map(str, paths),
                    "--export",
                    str(output),
                    "--interval",
                    "0",
                    "--delay",
                    "0",
                    "--loglevel",
                    "ERROR",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                timeout=15,
            )
            assert result.returncode == 0 and not result.stderr, result.stderr
            assert proxy.requests == [(2, 3, 40000, 1), (7, 3, 40000, 1)]
            assert not proxy.errors
            assert json.loads(output.read_text()) == {
                "first": {"value": 1},
                "second": {"value": 1},
            }
        finally:
            proxy.shutdown()
            thread.join(timeout=5)


@pytest.mark.parametrize("word_big", [True, False])
def test_numeric_bit_table_csv_parity_uses_complete_bytes(
    live_modsim, tmp_path, word_big
):
    import os

    baseline = os.environ.get("MODPOLL_1X_SOURCE")
    if not baseline:
        pytest.skip("requires installed v1 baseline")
    payload = b"ABC\x00"
    bits = [bool(byte & (1 << (7 - index))) for byte in payload for index in range(8)]
    client = ModbusTcpClient("127.0.0.1", port=live_modsim)
    try:
        assert client.connect()
        assert not client.write_coils(0, bits, device_id=1).isError()
    finally:
        client.close()
    document = meter_model("bits")
    document["properties"] = {}
    document["modpoll:acquisition"] = []
    rows = ["device,bits,1"]
    cases = [
        ("unsigned16", "uint16", 16, "integer"),
        ("unsigned32", "uint32", 32, "integer"),
        ("float32", "float32", 32, "number"),
        ("label", "string3", 24, "string"),
    ]
    for name, dtype, count, type_ in cases:
        form = raw_form(dtype, 0, quantity=count, entity="Coil")
        form.update(
            {
                "modv:mostSignificantByte": True,
                "modv:mostSignificantWord": word_big,
                "modpoll:bitPacking": "legacy-msb",
            }
        )
        document["properties"][name] = {
            "type": type_,
            "readOnly": True,
            "forms": [form],
        }
        document["modpoll:acquisition"].append(
            {
                "modv:entity": "Coil",
                "modv:address": 0,
                "modv:quantity": count,
                "modpoll:members": [name],
            }
        )
        rows += [
            f"poll,coil,0,{count},BE_" + ("BE" if word_big else "LE"),
            f"ref,{name},0,{dtype},r",
        ]
    csv = tmp_path / "bits.csv"
    csv.write_text("\n".join(rows) + "\n")
    model = tmp_path / "bits.tm.json"
    model.write_text(json.dumps(document))
    expected = {
        "bits": {
            "unsigned16": 0x4142,
            "unsigned32": 0x41424300,
            "float32": struct.unpack(">f", payload)[0],
            "label": "ABC",
        }
    }
    for label, executable, config in [
        ("csv", str(Path(baseline) / ".venv/bin/python"), csv),
        ("tm", sys.executable, model),
    ]:
        output = tmp_path / (label + ".json")
        result = subprocess.run(
            [
                executable,
                "-m",
                "modpoll",
                "--once",
                "--daemon",
                "--config",
                str(config),
                "--tcp",
                "127.0.0.1",
                "--tcp-port",
                str(live_modsim),
                "--interval",
                "0",
                "--delay",
                "0",
                "--export",
                str(output),
                "--loglevel",
                "ERROR",
            ],
            cwd=Path(baseline) if label == "csv" else ROOT,
            text=True,
            capture_output=True,
            timeout=15,
        )
        assert result.returncode == 0 and not result.stderr, result.stderr
        assert json.loads(output.read_text()) == expected
