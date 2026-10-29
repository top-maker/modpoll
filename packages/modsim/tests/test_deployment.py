"""Deployment isolation, scene updates, local hooks and bounded remote models."""

import asyncio
from io import BytesIO
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from unittest.mock import patch

import pytest
import yaml
from pymodbus.client import ModbusTcpClient

from modsim.manifest import load_deployment
from argparse import Namespace
from modsim.runtime import RuntimeContext
from modsim.sources import model_document

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "contrib/advantech/adam-6024/adam-6024.tm.json"


def device(unit=1, **options):
    return {
        "id": options.pop("name", f"io-{unit}"),
        "model": options.pop("model", str(MODEL)),
        "parameters": {"THING_ID": f"urn:modsim:test:{unit}", "UNIT_ID": unit},
        **options,
    }


def build(tmp_path, devices, **server):
    # The fixture creates version 2 declarations; initial values and scripts
    # belong to scenario documents, not deployment device fields.
    import copy

    devices = copy.deepcopy(devices)
    for index, spec in enumerate(devices):
        initial = spec.pop("initial", None)
        script = spec.pop("script", None)
        if initial is not None or script:
            scene = {"version": "1"}
            if initial is not None:
                scene["initial"] = initial
            if script:
                scene["script"] = script
            scene_path = tmp_path / f"fixture-scene-{index}.json"
            scene_path.write_text(json.dumps(scene))
            spec["scenario"] = str(scene_path)
    path = tmp_path / "deployment.yaml"
    path.write_text(
        yaml.safe_dump(
            {"version": 2, "name": "test-lab", "server": server, "devices": devices}
        )
    )
    deployment = load_deployment(path)
    runtimes = [
        item.build(allow_scripts=True) for item in deployment.instances.values()
    ]
    return Namespace(runtimes=runtimes, deployment=path)


def test_independent_units_and_atomic_invalid_writes(tmp_path):
    args = build(
        tmp_path,
        [device(1, initial={"AO0_RAW": 12}), device(2, initial={"AO0_RAW": 34})],
    )
    context = RuntimeContext(args.runtimes)

    async def check():
        assert await context.async_getValues(1, 3, 10) == [12]
        assert await context.async_getValues(2, 3, 10) == [34]
        assert await context.async_setValues(1, 16, 10, [56, 78]) is None
        assert await context.async_getValues(1, 3, 10, 2) == [56, 78]
        assert await context.async_getValues(2, 3, 10) == [34]
        assert await context.async_setValues(1, 16, 11, [9, 9]) is not None
        assert await context.async_getValues(1, 3, 10, 2) == [56, 78]
        assert await context.async_setValues(1, 6, 0, [9]) is not None
        assert await context.async_getValues(99, 3, 10) is not None

    asyncio.run(check())


@pytest.mark.parametrize(
    "devices", [[device(), device()], [device(), device(2, name="io-1")]]
)
def test_duplicate_instances_fail_before_listening(tmp_path, devices):
    with pytest.raises(ValueError, match="duplicate"):
        build(tmp_path, devices)


def test_relative_scenario_script_and_instance_state(tmp_path, monkeypatch):
    (tmp_path / "models").mkdir()
    (tmp_path / "models/io.tm.json").write_bytes(MODEL.read_bytes())
    (tmp_path / "scenes").mkdir()
    (tmp_path / "scenes/behavior.py").write_text(
        """counter = 0

def initialize(device):
    device.set("AI0_RAW", 42)

def tick(device, elapsed, dt):
    global counter
    counter += 1
    device.set("AI1_RAW", counter)

def on_write(device, changes):
    if "AO0_RAW" in changes:
        device.set("AI0_RAW", changes["AO0_RAW"])
"""
    )
    (tmp_path / "scenes/io.json").write_text(
        json.dumps({"version": "1", "script": "behavior.py"})
    )
    specs = [
        device(unit, model="models/io.tm.json", scenario="scenes/io.json")
        for unit in (1, 2)
    ]
    monkeypatch.chdir("/")
    args = build(tmp_path, specs)
    first, second = args.runtimes
    assert first.get("AI0_RAW") == 42
    first.advance(1, 1)
    assert first.get("AI1_RAW") == 2
    assert second.get("AI1_RAW") == 1
    asyncio.run(RuntimeContext(args.runtimes).async_setValues(1, 6, 10, [99]))
    assert first.get("AI0_RAW") == 99
    assert second.get("AI0_RAW") == 42


def test_script_requires_opt_in_and_unknown_fields_rejected(tmp_path):
    (tmp_path / "script.py").write_text('raise AssertionError("must not execute")')
    path = tmp_path / "denied.yaml"
    (tmp_path / "scene.json").write_text(
        json.dumps({"version": "1", "script": "script.py"})
    )
    path.write_text(
        yaml.safe_dump(
            {"version": 2, "name": "denied", "devices": [device(scenario="scene.json")]}
        )
    )
    with pytest.raises(ValueError, match="allow-scripts"):
        next(iter(load_deployment(path).instances.values())).build()
    with pytest.raises(ValueError, match="Additional properties"):
        build(tmp_path, [device(typo=True)])


def test_seeded_noise_and_client_write_policy(tmp_path):
    scenario = {
        "version": "1",
        "seed": 73,
        "generators": {"AO0_RAW": {"kind": "noise", "minimum": 1, "maximum": 100}},
    }
    (tmp_path / "scene.json").write_text(json.dumps(scenario))
    args = build(
        tmp_path, [device(1, scenario="scene.json"), device(2, scenario="scene.json")]
    )
    first, second = args.runtimes
    assert first.get("AO0_RAW") == second.get("AO0_RAW")
    first.advance(1, 1)
    second.advance(1, 1)
    assert first.get("AO0_RAW") == second.get("AO0_RAW")
    asyncio.run(RuntimeContext(args.runtimes).async_setValues(1, 6, 10, [777]))
    first.advance(2, 1)
    assert first.get("AO0_RAW") == 777
    first.write_policy = "overwrite"
    first.advance(3, 1)
    assert 1 <= first.get("AO0_RAW") <= 100


def test_internal_measurement_updates_and_failed_batch_are_atomic(tmp_path):
    instance = build(tmp_path, [device()]).runtimes[0]
    instance.set("AI0_RAW", 123)
    assert instance.get("AI0_RAW") == 123
    with pytest.raises(ValueError):
        instance.set_many({"AI0_RAW": 456, "AI1_RAW": -1})
    assert instance.get("AI0_RAW") == 123


def test_remote_model_uses_https_raw_and_shared_json_checks():
    class Response(BytesIO):
        def geturl(self):
            return "https://raw.githubusercontent.com/top-maker/modsim/v2/device.json"

    with patch(
        "modsim.sources.urlopen", return_value=Response(MODEL.read_bytes())
    ) as request:
        assert (
            model_document("https://github.com/top-maker/modsim/blob/v2/device.json")[
                "modpoll:version"
            ]
            == "0.2"
        )
        assert (
            request.call_args.args[0]
            == "https://raw.githubusercontent.com/top-maker/modsim/v2/device.json"
        )
    with patch("modsim.sources.urlopen", return_value=Response(b'{"a":1,"a":2}')):
        with pytest.raises(ValueError, match="duplicate"):
            model_document("https://example.com/model.json")
    with patch("modsim.sources.urlopen", return_value=Response(b" " * 1048577)):
        with pytest.raises(ValueError, match="exceeds"):
            model_document("https://example.com/model.json")
    with pytest.raises(ValueError, match="HTTPS"):
        model_document("http://example.com/model.json")


@pytest.mark.integration
def test_multi_device_listener_loopback_and_shutdown(tmp_path):
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    path = build(
        tmp_path,
        [
            device(1, initial={"AO0_RAW": 10}),
            device(
                2,
                scenario=str(ROOT / "contrib/advantech/adam-6024/simulation/io-loopback.sim.json"),
            ),
        ],
        port=port,
    ).deployment
    client = ModbusTcpClient("127.0.0.1", port=port, timeout=0.5, retries=0)
    with (tmp_path / "server.log").open("w+") as log:
        process = subprocess.Popen(
            [sys.executable, "-m", "modsim", "up", "-f", str(path)],
            cwd=tmp_path,
            env={**os.environ, "PYTHONPATH": str(ROOT)},
            stdout=log,
            stderr=log,
        )
        try:
            deadline = time.monotonic() + 8
            while not client.connect():
                if process.poll() is not None or time.monotonic() >= deadline:
                    log.seek(0)
                    pytest.fail(log.read())
                time.sleep(0.05)
            assert client.read_holding_registers(10, device_id=1).registers == [10]
            assert not client.write_register(10, 432, device_id=2).isError()
            assert client.read_input_registers(0, device_id=2).registers == [432]
            assert client.read_holding_registers(10, device_id=1).registers == [10]
            assert not client.write_coil(16, True, device_id=2).isError()
            assert client.read_discrete_inputs(0, device_id=2).bits[0] is True
            assert client.read_input_registers(0, device_id=3).isError()
            assert client.read_coils(18, device_id=2).isError()
        finally:
            client.close()
            process.terminate()
            process.wait(timeout=5)
        assert process.returncode == 0
    with socket.socket() as check:
        # Match server reuse semantics: TIME_WAIT is not a live listener.
        check.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        check.bind(("127.0.0.1", port))


def test_invalid_generator_envelope_and_binding_cycles_fail_at_startup(tmp_path):
    scene = tmp_path / "invalid.json"
    scene.write_text(
        json.dumps(
            {
                "version": "1",
                "generators": {
                    "AI0_RAW": {
                        "kind": "sine",
                        "center": 65530,
                        "amplitude": 10,
                        "period": 2,
                    }
                },
            }
        )
    )
    with pytest.raises(ValueError):
        build(tmp_path, [device(scenario=scene.name)])
    scene.write_text(
        json.dumps(
            {"version": "1", "bindings": {"AO0_RAW": "AO1_RAW", "AO1_RAW": "AO0_RAW"}}
        )
    )
    with pytest.raises(ValueError, match="chains/cycles"):
        build(tmp_path, [device(scenario=scene.name)])


def test_failed_write_hook_rolls_back_entire_device(tmp_path):
    args = build(tmp_path, [device(initial={"AO0_RAW": 11, "AI0_RAW": 22})])
    instance = args.runtimes[0]

    class FailingScript:
        @staticmethod
        def on_write(device, changes):
            device.set("AI0_RAW", 333)
            raise ValueError("invalid device command")

    instance.script = FailingScript
    assert (
        asyncio.run(RuntimeContext([instance]).async_setValues(1, 6, 10, [44]))
        is not None
    )
    assert instance.get("AO0_RAW") == 11
    assert instance.get("AI0_RAW") == 22
    assert not instance.held


def test_legacy_deployment_version_rejected(tmp_path):
    path = tmp_path / "deployment.yaml"
    path.write_text(json.dumps({"version": "1", "devices": []}))
    with pytest.raises(ValueError, match="version"):
        load_deployment(path)


def test_json_deployment_file_rejected(tmp_path):
    path = tmp_path / "deployment.json"
    path.write_text(json.dumps({"version": 2, "devices": []}))
    with pytest.raises(ValueError, match="must use .yaml or .yml"):
        load_deployment(path)


def test_explicit_thing_id_for_model_without_id(tmp_path):
    instance = build(tmp_path, [device()]).runtimes[0]
    deployment = load_deployment(tmp_path / "deployment.yaml")
    assert deployment.instances["io-1"].td["id"] == "urn:modsim:test:1"
    assert instance.unit_id == 1


def test_root_adam_deployment():
    deployment = load_deployment(ROOT / "examples/deployment.yaml")
    assert deployment.bind == "0.0.0.0"
    assert [item.model.unit_id for item in deployment.instances.values()] == [1, 2]
    assert all(
        item.model.endpoint == ("127.0.0.1", 5020)
        for item in deployment.instances.values()
    )


def test_removed_deployment_cli_option(tmp_path):
    result = subprocess.run(
        [sys.executable, "-m", "modsim", "--deployment", "old.json"],
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(ROOT)},
        capture_output=True,
        timeout=8,
    )
    assert result.returncode != 0
    assert b"unrecognized arguments: --deployment" in result.stderr
