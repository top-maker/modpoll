"""Managed deployment acceptance using independent TCP clients and CLI processes."""

import asyncio
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import uuid

import pytest
from modpoll_wot import parse_model, validate_standard
from pymodbus.client import ModbusTcpClient

from modsim.management import RuntimeManager
from modsim.manifest import load_deployment, read_yaml

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "contrib/advantech/adam-6024/adam-6024.tm.json"


def fixture(tmp_path):
    model = json.loads(SOURCE.read_text())
    model["id"] = "{{THING_ID}}"
    model["title"] = "{{TITLE}}"
    (tmp_path / "io.tm.json").write_text(json.dumps(model))
    (tmp_path / "scene.json").write_text(
        json.dumps({"version": "1", "initial": {"AO0_RAW": 12}})
    )
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    spec = {
        "version": 2,
        "name": "test-" + uuid.uuid4().hex[:16],
        "server": {"bind": "127.0.0.1", "port": port},
        "devices": [device(1)],
    }
    path = tmp_path / "deployment.yaml"
    write(path, spec)
    return path, spec, port


def device(unit):
    return {
        "id": f"io-{unit}",
        "model": "io.tm.json",
        "parameters": {
            "THING_ID": f"urn:modsim:test:io-{unit}",
            "TITLE": f"I/O {unit}",
            "UNIT_ID": unit,
        },
        "scenario": "scene.json",
    }


def write(path, spec):
    # JSON is a valid YAML document; a separate test exercises YAML syntax.
    path.write_text(json.dumps(spec))


def cli(path, *args, check=True):
    result = subprocess.run(
        [sys.executable, "-m", "modsim", *args, "-f", str(path)],
        cwd=path.parent,
        env={**os.environ, "PYTHONPATH": str(ROOT), "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True,
        text=True,
        timeout=45,
    )
    if check:
        assert result.returncode == 0, result.stderr + result.stdout
    return result


def test_yaml_rejects_duplicates_aliases_nonfinite_and_deep_input(tmp_path):
    path = tmp_path / "deployment.yaml"
    for payload, error in [
        ("version: 2\nversion: 2", "duplicate"),
        ("a: &a [1]\nb: *a", "aliases"),
        ("a: .nan", "finite"),
        ("a: " + "[" * 70 + "0" + "]" * 70, "nesting"),
        ("a: 2026-10-29", "JSON-compatible"),
    ]:
        path.write_text(payload)
        with pytest.raises(ValueError, match=error):
            read_yaml(path)


def test_yaml_defaults_and_stable_standard_td(tmp_path):
    path, spec, port = fixture(tmp_path)
    path.write_text(
        "version: 2\nname: lab\nserver:\n  port: " + str(port) + "\ndevices:\n"
        "  - id: io-1\n    model: io.tm.json\n    parameters:\n"
        "      THING_ID: urn:modsim:test:io-1\n      TITLE: 一号设备\n      UNIT_ID: 7\n"
    )
    desired = load_deployment(path)
    instance = desired.instances["io-1"]
    validate_standard(instance.td, kind="td")
    assert parse_model(instance.td).unit_id == 7
    assert instance.td["title"] == "一号设备"
    assert instance.model.endpoint == ("127.0.0.1", port)
    assert instance.td == load_deployment(path).instances["io-1"].td


@pytest.mark.parametrize(
    "change,match",
    [
        ("duplicate-unit", "duplicate"),
        ("duplicate-id", "duplicate"),
        ("duplicate-td", "duplicate"),
        ("unknown-parameter", "unused"),
        ("missing-parameter", "unbound"),
        ("wildcard", "requires parameters.HOST"),
        ("missing-id", "stable TD id"),
    ],
)
def test_invalid_instances_fail_before_start(tmp_path, change, match):
    path, spec, _ = fixture(tmp_path)
    other = device(2)
    if change == "duplicate-unit":
        other["parameters"]["UNIT_ID"] = 1
    elif change == "duplicate-id":
        other["id"] = "io-1"
    elif change == "duplicate-td":
        other["parameters"]["THING_ID"] = "urn:modsim:test:io-1"
    elif change == "unknown-parameter":
        other["parameters"]["TYPO"] = 3
    elif change == "missing-parameter":
        del other["parameters"]["TITLE"]
    elif change == "wildcard":
        spec["server"]["bind"] = "0.0.0.0"
    elif change == "missing-id":
        model = json.loads((tmp_path / "io.tm.json").read_text())
        del model["id"]
        del other["parameters"]["THING_ID"]
        del spec["devices"][0]["parameters"]["THING_ID"]
        (tmp_path / "io.tm.json").write_text(json.dumps(model))
    spec["devices"].append(other)
    write(path, spec)
    with pytest.raises(ValueError, match=match):
        load_deployment(path)


def test_snapshot_reset_reconcile_and_cleanup(tmp_path):
    path, spec, _ = fixture(tmp_path)

    async def exercise():
        manager = RuntimeManager()
        try:
            await manager.apply(load_deployment(path))
            original = manager.devices["io-1"]
            original.set("AO0_RAW", 99)
            await manager.apply(load_deployment(path))
            assert manager.devices["io-1"] is original
            assert original.get("AO0_RAW") == 99
            spec["devices"].append(device(2))
            write(path, spec)
            await manager.apply(load_deployment(path))
            assert manager.devices["io-1"] is original
            retired = manager.tasks["io-2"]
            spec["devices"].pop()
            write(path, spec)
            await manager.apply(load_deployment(path))
            assert retired.done()
            assert 2 not in manager.context.devices
            (tmp_path / "scene.json").write_text("invalid on disk")
            await manager.reset("io-1")
            assert manager.devices["io-1"].get("AO0_RAW") == 12
        finally:
            await manager.close()
        assert all(task.done() for task in manager.tasks.values())

    asyncio.run(exercise())


def test_dry_run_never_executes_scripts_and_failures_preserve_live_state(tmp_path):
    path, spec, _ = fixture(tmp_path)
    marker = tmp_path / "executed"
    (tmp_path / "behavior.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).touch()\n"
        "def initialize(device):\n    raise RuntimeError('candidate failed')\n"
    )

    async def exercise():
        manager = RuntimeManager(allow_scripts=True)
        try:
            await manager.apply(load_deployment(path))
            original = manager.devices["io-1"]
            (tmp_path / "scene.json").write_text(
                json.dumps({"version": "1", "script": "behavior.py"})
            )
            desired = load_deployment(path)
            plan = await manager.apply(desired, dry_run=True)
            assert plan["replaced"] == ["io-1"]
            assert not marker.exists()
            with pytest.raises(RuntimeError, match="candidate failed"):
                await manager.apply(desired)
            assert manager.devices["io-1"] is original
            assert manager.context.devices[1] is original
        finally:
            await manager.close()

    asyncio.run(exercise())


@pytest.mark.integration
def test_cli_live_add_remove_replace_export_reset_and_rollback(tmp_path):
    path, spec, port = fixture(tmp_path)
    client = ModbusTcpClient("127.0.0.1", port=port, timeout=1, retries=0)
    try:
        cli(path, "up", "-d")
        first_pid = json.loads(cli(path, "ps").stdout)["pid"]
        assert client.connect()
        assert not client.write_register(10, 99, device_id=1).isError()
        cli(path, "up", "-d")
        assert client.read_holding_registers(10, device_id=1).registers == [99]
        spec["devices"].append(device(2))
        write(path, spec)
        cli(path, "up", "--dry-run")
        assert client.read_holding_registers(10, device_id=2).isError()
        cli(path, "up", "-d")
        assert client.read_holding_registers(10, device_id=2).registers == [12]
        assert client.read_holding_registers(10, device_id=1).registers == [99]
        # Invalid update cannot retire either live instance.
        spec["devices"][1]["parameters"]["UNIT_ID"] = 1
        write(path, spec)
        assert cli(path, "up", "-d", check=False).returncode == 2
        assert client.read_holding_registers(10, device_id=2).registers == [12]
        spec["devices"].pop()
        write(path, spec)
        cli(path, "up", "-d")
        assert client.read_holding_registers(10, device_id=2).isError()
        assert client.read_holding_registers(10, device_id=1).registers == [99]
        cli(path, "reset", "--device", "io-1")
        assert client.read_holding_registers(10, device_id=1).registers == [12]
        # Export the applied version while on-disk parameters have drifted.
        spec["devices"][0]["parameters"]["TITLE"] = "Changed offline"
        write(path, spec)
        live, offline = tmp_path / "live.json", tmp_path / "offline.json"
        cli(path, "export", "--running", "--device", "io-1", "-o", str(live))
        cli(path, "export", "--device", "io-1", "-o", str(offline))
        assert json.loads(live.read_text())["title"] == "I/O 1"
        assert json.loads(offline.read_text())["title"] == "Changed offline"
        assert not client.write_register(10, 77, device_id=1).isError()
        cli(path, "up", "-d")
        assert client.read_holding_registers(10, device_id=1).registers == [12]
        assert json.loads(cli(path, "ps").stdout)["pid"] == first_pid
        # Listener changes explicitly require down/up.
        spec["server"]["port"] = port + 1 if port < 65535 else port - 1
        write(path, spec)
        assert "run down" in cli(path, "up", "-d", check=False).stderr
        # Same-name deployments cannot take control from another file.
        conflict = tmp_path / "other.yaml"
        write(conflict, spec)
        assert "different file" in cli(conflict, "up", "-d", check=False).stderr
        spec["server"]["port"] = port
        spec["devices"] = []
        write(path, spec)
        cli(path, "up", "-d")
        assert client.read_holding_registers(10, device_id=1).isError()
        spec["devices"] = [device(1)]
        write(path, spec)
        cli(path, "up", "-d")
        assert client.read_holding_registers(10, device_id=1).registers == [12]
        assert cli(path, "logs").stdout
    finally:
        client.close()
        cli(path, "down")
    assert json.loads(cli(path, "ps").stdout)["running"] is False
    cli(path, "down")
    with socket.socket() as check:
        # Match server reuse semantics: TIME_WAIT is not a live listener.
        check.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        check.bind(("127.0.0.1", port))


def test_offline_export_requires_no_process_and_does_not_run_behavior(tmp_path):
    path, spec, _ = fixture(tmp_path)
    (tmp_path / "fail.py").write_text("raise RuntimeError('must not execute')")
    (tmp_path / "scene.json").write_text(
        json.dumps({"version": "1", "script": "fail.py"})
    )
    output = tmp_path / "tds"
    cli(path, "export", "--output-dir", str(output))
    td = json.loads((output / "io-1.td.json").read_text())
    validate_standard(td, kind="td")
    assert parse_model(td).unit_id == 1


def test_reset_uses_pristine_script_parameters(tmp_path):
    path, spec, _ = fixture(tmp_path)
    (tmp_path / "behavior.py").write_text(
        "def initialize(device):\n"
        "    device.parameters['counter'] += 1\n"
        "    device.set('AO0_RAW', device.parameters['counter'])\n"
    )
    (tmp_path / "scene.json").write_text(
        json.dumps(
            {"version": "1", "parameters": {"counter": 0}, "script": "behavior.py"}
        )
    )

    async def exercise():
        manager = RuntimeManager(allow_scripts=True)
        try:
            await manager.apply(load_deployment(path))
            assert manager.devices["io-1"].get("AO0_RAW") == 1
            await manager.reset("io-1")
            assert manager.devices["io-1"].get("AO0_RAW") == 1
        finally:
            await manager.close()

    asyncio.run(exercise())


def test_managed_behavior_failure_isolated_and_not_revived_by_unchanged_up(tmp_path):
    path, spec, _ = fixture(tmp_path)
    (tmp_path / "fail.py").write_text(
        "def tick(device, elapsed, dt):\n"
        "    if elapsed > 0:\n"
        "        raise RuntimeError('failed device')\n"
    )
    (tmp_path / "fail.json").write_text(
        json.dumps({"version": "1", "tick": 0.001, "script": "fail.py"})
    )
    spec["devices"][0]["scenario"] = "fail.json"
    spec["devices"].append(device(2))
    write(path, spec)

    async def exercise():
        manager = RuntimeManager(allow_scripts=True)
        try:
            await manager.apply(load_deployment(path))
            await asyncio.wait_for(manager.tasks["io-1"], 2)
            assert 1 not in manager.context.devices
            assert 2 in manager.context.devices
            assert manager.status()["devices"][0]["state"] == "failed"
            original = manager.tasks["io-1"]
            await manager.apply(load_deployment(path))
            assert 1 not in manager.context.devices
            assert manager.tasks["io-1"] is original
            await manager.reset("io-1")
            assert manager.tasks["io-1"] is not original
        finally:
            await manager.close()

    asyncio.run(exercise())


def test_export_does_not_require_scenario_files(tmp_path):
    path, spec, _ = fixture(tmp_path)
    (tmp_path / "scene.json").unlink()
    output = tmp_path / "instance.td.json"
    cli(path, "export", "--device", "io-1", "-o", str(output))
    assert parse_model(json.loads(output.read_text())).unit_id == 1


@pytest.mark.integration
def test_default_file_foreground_signal_cleanup(tmp_path):
    import time

    path, spec, port = fixture(tmp_path)
    with (tmp_path / "foreground.log").open("w+") as log:
        process = subprocess.Popen(
            [sys.executable, "-m", "modsim", "up"],
            cwd=tmp_path,
            env={**os.environ, "PYTHONPATH": str(ROOT)},
            stdout=log,
            stderr=log,
        )
        try:
            deadline = time.monotonic() + 10
            while True:
                if process.poll() is not None:
                    log.seek(0)
                    pytest.fail(log.read())
                status = json.loads(cli(path, "ps").stdout)
                if status["running"]:
                    break
                assert time.monotonic() < deadline
                time.sleep(0.05)
        finally:
            process.terminate()
            process.wait(timeout=10)
        assert process.returncode == 0
    assert json.loads(cli(path, "ps").stdout)["running"] is False
    with socket.socket() as check:
        # Match server reuse semantics: TIME_WAIT is not a live listener.
        check.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        check.bind(("127.0.0.1", port))


@pytest.mark.integration
def test_attached_up_and_follow_logs_detach_without_stopping(tmp_path):
    import signal
    import time

    path, _, _ = fixture(tmp_path)
    cli(path, "up", "-d")
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    try:
        for command in (["up"], ["logs", "--follow"]):
            with (tmp_path / "output.log").open("w+") as output:
                process = subprocess.Popen(
                    [sys.executable, "-m", "modsim", *command, "-f", str(path)],
                    cwd=tmp_path,
                    env=env,
                    stdout=output,
                    stderr=output,
                )
                try:
                    deadline = time.monotonic() + 10
                    while time.monotonic() < deadline:
                        output.flush()
                        if (tmp_path / "output.log").stat().st_size:
                            break
                        assert process.poll() is None
                        time.sleep(0.05)
                    else:
                        pytest.fail("attached command did not print logs")
                    assert process.poll() is None
                finally:
                    process.send_signal(signal.SIGINT)
                    process.wait(timeout=5)
                assert json.loads(cli(path, "ps").stdout)["running"] is True
    finally:
        cli(path, "down")
