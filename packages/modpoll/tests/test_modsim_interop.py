import json
from pathlib import Path

"""Cross-project TCP regression; set MODSIM_PYTHON and MODSIM_SOURCE to opt in."""

import os
import socket
import subprocess
import time

import pytest

from modpoll.arg_parser import get_parser
from modpoll.modbus_task import setup_modbus_handlers

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.environ.get("MODSIM_PYTHON") or not os.environ.get("MODSIM_SOURCE"),
        reason="requires a separate modsim environment",
    ),
]


def test_four_table_reads_and_fc5_fc6_fc16_writes(tmp_path):
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = env["MODSIM_SOURCE"]
    process = subprocess.Popen(
        [env["MODSIM_PYTHON"], "-m", "modsim", "--port", str(port), "--log", "error"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    handlers = []
    try:
        deadline = time.monotonic() + 10
        while True:
            if process.poll() is not None:
                pytest.fail("simulator exited during startup")
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                    break
            except OSError:
                if time.monotonic() >= deadline:
                    pytest.fail("simulator did not start")
                time.sleep(0.05)
        config = tmp_path / "meter.tm.json"
        model = json.loads(
            (
                Path(__file__).resolve().parents[1] / "examples/modsim.tm.json"
            ).read_text()
        )
        model["title"] = "meter"
        config.write_text(json.dumps(model))
        args = get_parser().parse_args(
            [
                "--config",
                str(config),
                "--tcp",
                "127.0.0.1",
                "--tcp-port",
                str(port),
                "--unit-id",
                "7",
                "--daemon",
                "--interval",
                "0",
            ]
        )
        handlers = setup_modbus_handlers(args)
        handler = handlers[0]
        handler.poll()
        device = handler.get_device_list()[0]
        bits = [True, False, True, False, False, False, False, True]
        assert device.points["coil01-08"].val == bits
        assert device.points["coil09-16"].val == bits
        assert device.points["di01-08"].val == bits
        assert device.points["input_reg01"].val == 1
        assert device.points["holding_reg01"].val == 1
        assert handler.write_coil("meter", 1, True)
        assert handler.write_register("meter", 40000, 123)
        assert handler.write_register("meter", 40001, [12, 13, 14])
        handler.poll()
        assert device.points["coil01-08"].val[1] is True
        assert device.points["holding_reg01"].val == 123
        assert handler.connect()
        result = handler.modbus_client.read_holding_registers(
            40000, count=4, device_id=7
        )
        assert not result.isError()
        assert result.registers == [123, 12, 13, 14]
    finally:
        for handler in handlers:
            handler.close()
        process.terminate()
        process.wait(timeout=5)
        assert process.returncode == 0
