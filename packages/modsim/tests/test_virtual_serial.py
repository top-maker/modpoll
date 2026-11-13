"""RTU simulation over a virtual serial port (SIM-04)."""

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

import pytest

from modsim.main import read_command
from modsim.utils import get_parser

MODEL = Path(__file__).parent / "fixtures/io-module/adam-6024.tm.json"
VALUES = [0x1234, 0x8001, 0xABCD, 0, 65535, 42]
posix_only = pytest.mark.skipif(os.name == "nt", reason="needs pseudo-terminals")


def _start(tmp_path, *extra):
    data = tmp_path / "initial.data.json"
    data.write_text(
        json.dumps(
            {"version": "1", "initial": {f"AI{i}_RAW": v for i, v in enumerate(VALUES)}}
        )
    )
    log = (tmp_path / "server.log").open("w+")
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "modsim",
            "--config",
            str(MODEL),
            "--unit-id",
            "1",
            "--data",
            str(data),
            "--serial",
            "pty",
            *extra,
        ],
        cwd=tmp_path,
        stdout=log,
        stderr=log,
    )
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        log.seek(0)
        text = log.read()
        found = re.search(r"Virtual serial port for the client: (\S+)", text)
        if found:
            return process, found.group(1)
        if process.poll() is not None:
            pytest.fail(text)
        time.sleep(0.1)
    process.kill()
    pytest.fail("virtual serial startup timed out")


@posix_only
def test_model_is_read_over_the_virtual_port_and_cleaned_up(tmp_path):
    from pymodbus.client import ModbusSerialClient

    link = tmp_path / "ttyV0"
    process, port = _start(tmp_path, "--serial-link", str(link))
    try:
        assert link.is_symlink() and os.readlink(link) == port
        # The same server survives a client opening and closing the port twice.
        for _ in range(2):
            client = ModbusSerialClient(port, baudrate=9600, timeout=2)
            assert client.connect()
            try:
                reply = client.read_input_registers(0, count=6, device_id=1)
                assert not reply.isError()
                assert reply.registers == VALUES
            finally:
                client.close()
    finally:
        process.terminate()
        process.wait(timeout=10)
    assert not link.is_symlink()


def test_read_command_names_the_virtual_port():
    args = get_parser().parse_args(
        ["--config", "m.tm.json", "--serial", "pty", "--unit-id", "7"]
    )
    args.serial_baud, args.serial_parity = 9600, "even"
    assert read_command(args, "/dev/pts/9") == (
        "modpoll --config m.tm.json --serial /dev/pts/9 --serial-baud 9600"
        " --serial-parity even --unit-id 7"
    )


@pytest.mark.parametrize(
    "arguments",
    [
        ["--serial", "pty", "--port", "5020"],
        ["--serial", "pty", "--comm", "tcp"],
        ["--serial-baud", "9600"],
        ["--serial", "/dev/ttyUSB0", "--serial-link", "x"],
    ],
)
def test_conflicting_serial_options_are_refused(monkeypatch, arguments):
    from modsim.utils import get_commandline

    monkeypatch.setattr(sys, "argv", ["modsim", *arguments])
    with pytest.raises(SystemExit) as error:
        get_commandline()
    assert error.value.code == 2
