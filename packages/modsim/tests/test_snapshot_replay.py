"""modpoll reads a simulated device, exports a snapshot, and modsim replays it.

Runs when MODSIM_TEST_MODPOLL_PYTHON names a Python environment with modpoll
installed; modsim and modpoll stay independent installations.
"""

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

import pytest

MODPOLL = os.environ.get("MODSIM_TEST_MODPOLL_PYTHON")
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not MODPOLL, reason="MODSIM_TEST_MODPOLL_PYTHON is not set"),
]
ROOT = Path(__file__).resolve().parents[1]


def register(raw, address, quantity=1, multiplier=None, kind="number"):
    form = {
        "op": "readproperty",
        "modv:entity": "HoldingRegister",
        "modv:address": address,
        "modv:quantity": quantity,
        "modv:type": "xsd:" + raw,
    }
    if multiplier is not None:
        form["modpoll:multiplier"] = multiplier
    return {"type": kind, "readOnly": True, "forms": [form]}


MODEL = {
    "@context": [
        "https://www.w3.org/2022/wot/td/v1.1",
        {
            "modpoll": "https://top-maker.github.io/modpoll/vocab/wot-modbus#",
            "modv": "https://www.w3.org/2019/wot/modbus",
            "xsd": "http://www.w3.org/2001/XMLSchema#",
        },
    ],
    "@type": "tm:ThingModel",
    "title": "replay-meter",
    "modpoll:version": "0.2",
    "properties": {
        "VOLTAGE": register("unsignedShort", 0, multiplier="0.1"),
        "CURRENT": register("short", 1, multiplier="0.001"),
        "ENERGY": register("unsignedInt", 2, 2, multiplier="0.01"),
        "FREQUENCY": register("float", 4, 2),
        "STATUS": register("unsignedShort", 6, kind="integer"),
    },
    "modpoll:acquisition": [
        {
            "modv:entity": "HoldingRegister",
            "modv:address": 0,
            "modv:quantity": 7,
            "modpoll:members": ["VOLTAGE", "CURRENT", "ENERGY", "FREQUENCY", "STATUS"],
        }
    ],
}
# 230.1 and 4.987 read back as 230.10000000000002 and 4.987 with float scaling;
# the replay must serve whatever modpoll exported.
INITIAL = {
    "VOLTAGE": 230.1,
    "CURRENT": -4.987,
    "ENERGY": 123456.78,
    "FREQUENCY": 50.0,
    "STATUS": 4660,
}


def serve_and_read(tmp_path, model, data, name):
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    with (tmp_path / f"{name}.log").open("w+") as log:
        server = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "modsim",
                "--config",
                str(model),
                "--data",
                str(data),
                "--bind",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            cwd=tmp_path,
            env=env,
            stdout=log,
            stderr=log,
        )
        try:
            deadline = time.monotonic() + 30
            while True:
                if server.poll() is not None:
                    log.seek(0)
                    raise AssertionError(log.read())
                try:
                    socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
                    break
                except OSError:
                    assert time.monotonic() < deadline, "modsim did not start"
                    time.sleep(0.1)
            snapshot = tmp_path / f"{name}.snapshot.json"
            subprocess.run(
                [
                    MODPOLL,
                    "-m",
                    "modpoll",
                    "--config",
                    str(model),
                    "--tcp",
                    "127.0.0.1",
                    "--tcp-port",
                    str(port),
                    "--once",
                    "--export",
                    str(snapshot),
                ],
                check=True,
                capture_output=True,
                timeout=60,
            )
            return snapshot
        finally:
            server.terminate()
            server.wait(timeout=10)


def test_exported_snapshot_replays_unchanged(tmp_path):
    model = tmp_path / "replay.tm.json"
    model.write_text(json.dumps(MODEL))
    data = tmp_path / "initial.data.json"
    data.write_text(json.dumps({"version": "1", "initial": INITIAL}))

    first = serve_and_read(tmp_path, model, data, "first")
    exported = json.loads(first.read_text())["replay-meter"]
    # modpoll exports the exact decimal of a scaled reading. Releases up to 2.0.0a5 exported
    # float(raw) * multiplier (230.10000000000002); modpoll-wot's scaled_raw property tests
    # show that form maps back to the same raw value too.
    assert exported["VOLTAGE"] == 230.1
    assert exported["STATUS"] == 4660

    replayed = serve_and_read(tmp_path, model, first, "replay")
    assert json.loads(replayed.read_text()) == json.loads(first.read_text())
