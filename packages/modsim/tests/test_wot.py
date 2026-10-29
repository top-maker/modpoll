"""First raw-I/O model slice: native addressing, initialization and isolation."""

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

import pytest
from pymodbus.client import ModbusTcpClient

pytest.importorskip(
    "modpoll_wot.profile",
    reason="install candidate tool wheel for configured-device tests",
)
ROOT = Path(__file__).resolve().parents[1]


def model(entity="InputRegister", start=1, names=None):
    names = names or [f"AI{i}_RAW" for i in range(8)]
    bits = entity in ("Coil", "DiscreteInput")
    ro = entity in ("InputRegister", "DiscreteInput")
    properties = {}
    for offset, name in enumerate(names):
        prop = {
            "type": "boolean" if bits else "integer",
            "forms": [
                {
                    "modv:entity": entity,
                    "modv:address": start + offset,
                    "modv:quantity": 1,
                    "modv:type": "xsd:boolean" if bits else "xsd:unsignedShort",
                }
            ],
        }
        if ro:
            prop["readOnly"] = True
        if not bits:
            prop.update({"minimum": 0, "maximum": 65535})
        properties[name] = prop
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
        "title": "raw-fixture",
        "modpoll:version": "0.2",
        "properties": properties,
        "modpoll:acquisition": [
            {
                "modv:entity": entity,
                "modv:address": start,
                "modv:quantity": len(names),
                "modpoll:members": names,
            }
        ],
    }


@pytest.fixture
def server(tmp_path):
    running = []

    def start(document, *arguments):
        source = tmp_path / f"model-{len(running)}.json"
        source.write_text(json.dumps(document))
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        env = dict(
            os.environ,
            PYTHONPATH=str(ROOT) + os.pathsep + os.environ.get("PYTHONPATH", ""),
        )
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "modsim",
                "--config",
                str(source),
                "--bind",
                "127.0.0.1",
                "--port",
                str(port),
                "--unit-id",
                "1",
                "--log",
                "error",
                *arguments,
            ],
            cwd=ROOT,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        client = ModbusTcpClient("127.0.0.1", port=port, timeout=0.5, retries=0)
        running.append((process, client, port))
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            if process.poll() is not None:
                pytest.fail(process.stderr.read().decode())
            if client.connect():
                break
            time.sleep(0.05)
        else:
            pytest.fail("configured device did not start")
        return client

    yield start
    for process, client, port in running:
        client.close()
        process.terminate()
        process.wait(timeout=5)
        process.stderr.close()
        assert process.returncode == 0
        with socket.socket() as check:
            check.bind(("127.0.0.1", port))


@pytest.mark.integration
def test_input_model_reads_bounds_rejects_writes_and_does_not_share_units(server):
    client = server(model(), "--initial", "AI0_RAW=1234", "--initial", "AI7_RAW=65535")
    expected = [1234, 0, 0, 0, 0, 0, 0, 65535]
    assert client.read_input_registers(1, count=8, device_id=1).registers == expected
    assert client.read_input_registers(8, count=1, device_id=1).registers == [65535]
    assert client.read_input_registers(0, count=1, device_id=1).isError()
    assert client.read_input_registers(8, count=2, device_id=1).isError()
    assert client.read_coils(0, count=1, device_id=1).isError()
    assert client.write_coil(0, True, device_id=1).isError()
    assert client.write_register(1, 42, device_id=1).isError()
    assert client.write_registers(1, [42, 43], device_id=1).isError()
    assert client.read_input_registers(1, count=8, device_id=2).isError()
    assert client.read_input_registers(1, count=8, device_id=1).registers == expected


@pytest.mark.integration
def test_native_writable_registers_are_atomic_and_bits_do_not_leak_padding(server):
    client = server(model("HoldingRegister", 10, ["AO0", "AO1"]))
    assert not client.write_registers(10, [123, 456], device_id=1).isError()
    assert client.read_holding_registers(10, count=2, device_id=1).registers == [
        123,
        456,
    ]
    assert client.write_registers(11, [111, 222], device_id=1).isError()
    assert client.read_holding_registers(10, count=2, device_id=1).registers == [
        123,
        456,
    ]
    bits = server(model("Coil", 16, ["DO0", "DO1"]))
    assert not bits.write_coils(16, [True, False], device_id=1).isError()
    assert bits.read_coils(16, count=2, device_id=1).bits[:2] == [True, False]
    assert bits.read_coils(15, count=1, device_id=1).isError()
    assert bits.read_coils(18, count=1, device_id=1).isError()
    assert bits.read_coils(17, count=2, device_id=1).isError()
    assert bits.write_coils(17, [True, True], device_id=1).isError()
    assert bits.read_coils(16, count=2, device_id=1).bits[:2] == [True, False]


@pytest.mark.parametrize(
    "initial", ["AI0_RAW=-1", "AI0_RAW=65536", "AI0_RAW=true", "UNKNOWN=1"]
)
def test_invalid_initials_fail_before_binding(tmp_path, initial):
    from modsim.wot import configure
    from modsim.utils import get_parser

    path = tmp_path / "device.json"
    path.write_text(json.dumps(model()))
    args = get_parser().parse_args(["--config", str(path), "--initial", initial])
    with pytest.raises(ValueError):
        configure(args)


def test_defaults_and_constraints_are_respected(tmp_path):
    from modsim.wot import configure
    from modsim.utils import get_parser

    d = model()
    d["properties"]["AI0_RAW"].update({"minimum": 100, "maximum": 200, "multipleOf": 7})
    d["properties"]["AI1_RAW"]["default"] = 99
    path = tmp_path / "constrained.json"
    path.write_text(json.dumps(d))
    args = get_parser().parse_args(["--config", str(path)])
    configure(args)
    assert args.model_initialization["values"]["AI0_RAW"] == 105
    assert args.model_initialization["values"]["AI1_RAW"] == 99
    assert (
        args.model_initialization["origins"]["AI0_RAW"]
        == "synthetic type/constraint fallback"
    )
