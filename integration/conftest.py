"""Run the workspace's own modsim and modpoll against each other (SIM-08)."""

from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import time

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "packages/modpoll-wot/tests/fixtures"
MODEL = FIXTURES / "conformance.tm.json"
DATA = FIXTURES / "conformance.data.json"


def free_port():
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        return reservation.getsockname()[1]


@contextmanager
def simulator(tmp_path, transport, model=MODEL, data=DATA):
    """Start modsim on a free TCP port or a virtual serial port; yield the client's address."""
    log_path = tmp_path / f"modsim-{transport}.log"
    command = [
        sys.executable,
        "-m",
        "modsim",
        "--config",
        str(model),
        "--data",
        str(data),
    ]
    port = free_port() if transport == "tcp" else None
    command += ["--port", str(port)] if port else ["--serial", "pty"]
    with log_path.open("w+") as log:
        process = subprocess.Popen(command, stdout=log, stderr=log, cwd=tmp_path)
        try:
            deadline = time.monotonic() + 30
            while True:
                if process.poll() is not None:
                    log.seek(0)
                    pytest.fail(log.read())
                if port:
                    try:
                        socket.create_connection(("127.0.0.1", port), timeout=1).close()
                        address = port
                        break
                    except OSError:
                        pass
                else:
                    log.seek(0)
                    found = re.search(
                        r"Virtual serial port for the client: (\S+)", log.read()
                    )
                    if found:
                        address = found.group(1)
                        break
                if time.monotonic() > deadline:
                    pytest.fail(f"modsim did not start over {transport}")
                time.sleep(0.1)
            yield address
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def endpoint_arguments(transport, address):
    if transport == "tcp":
        return ["--tcp", "127.0.0.1", "--tcp-port", str(address)]
    return ["--rtu", address, "--rtu-baud", "9600"]


def run_modpoll(tmp_path, arguments):
    result = subprocess.run(
        [sys.executable, "-m", "modpoll", "--once", *arguments],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=tmp_path,
        stdin=subprocess.DEVNULL,
    )
    return result


def read_values(tmp_path, transport, address, model=MODEL):
    output = tmp_path / f"values-{transport}.json"
    result = run_modpoll(
        tmp_path,
        [
            *endpoint_arguments(transport, address),
            "--config",
            str(model),
            "--export",
            str(output),
        ],
    )
    assert result.returncode == 0, result.stdout + result.stderr
    (values,) = json.loads(output.read_text()).values()
    return values


TRANSPORTS = [
    "tcp",
    pytest.param(
        "rtu",
        marks=pytest.mark.skipif(
            os.name == "nt", reason="virtual serial ports need POSIX"
        ),
    ),
]
