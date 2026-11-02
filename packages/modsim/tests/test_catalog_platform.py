"""Opt-in installed CLI smoke against a pinned public TM on each supported OS."""

import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import sys
import time

import pytest
import yaml

pytestmark = pytest.mark.skipif(
    os.environ.get("MODSIM_CATALOG_PLATFORM") != "1",
    reason="Opt-in public URL/platform acceptance; see acceptance.yaml",
)


def test_remote_model_single_device_read_and_stop(tmp_path):
    lock = yaml.safe_load(
        (Path(__file__).resolve().parents[1] / "examples/model-source.yaml").read_text()
    )
    url = f"https://raw.githubusercontent.com/{lock['repository']}/{lock['revision']}/advantech/adam-5017uh/adam-5017uh.tm.json"
    scenario = tmp_path / "initial.sim.json"
    values = [0x1234, 0x8001, 0xABCD, 0, 65535, 42, 0x0102, 0xFE01]
    scenario.write_text(
        json.dumps(
            {"version": "1", "initial": {f"AI{i}_RAW": v for i, v in enumerate(values)}}
        )
    )
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    with (tmp_path / "server.log").open("w+") as log:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "modsim",
                "--config",
                url,
                "--bind",
                "127.0.0.1",
                "--port",
                str(port),
                "--unit-id",
                "1",
                "--scenario",
                str(scenario),
            ],
            cwd=tmp_path,
            env=env,
            stdout=log,
            stderr=log,
        )
        try:
            deadline = time.monotonic() + 30
            while True:
                if process.poll() is not None:
                    log.seek(0)
                    pytest.fail(log.read())
                try:
                    stream = socket.create_connection(("127.0.0.1", port), timeout=2)
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        pytest.fail("Single-device startup timed out")
                    time.sleep(0.1)
            with stream:
                stream.sendall(struct.pack(">HHHBBHH", 7, 0, 6, 1, 4, 1, 8))
                response = b""
                while len(response) < 25:
                    part = stream.recv(25 - len(response))
                    assert part
                    response += part
                assert response == struct.pack(">HHHBBB8H", 7, 0, 19, 1, 4, 16, *values)
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        # Stop means the foreground child is gone and its endpoint is closed.
        assert process.poll() is not None
        with pytest.raises(OSError):
            socket.create_connection(("127.0.0.1", port), timeout=1)
