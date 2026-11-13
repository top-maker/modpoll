"""Opt-in, isolated simulator fixture shared by protocol acceptance tests."""

import os
import socket
import subprocess
import time

import pytest


@pytest.fixture
def live_modsim():
    executable = os.environ.get("MODSIM_PYTHON")
    source = os.environ.get("MODSIM_SOURCE")
    if not executable or not source:
        pytest.skip("requires MODSIM_PYTHON and MODSIM_SOURCE")
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    process = subprocess.Popen(
        [executable, "-m", "modsim", "--port", str(port), "--log", "error"],
        cwd=source,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    try:
        deadline = time.monotonic() + 10
        while True:
            if process.poll() is not None:
                pytest.fail("modsim exited: " + process.stderr.read().decode())
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                    break
            except OSError:
                if time.monotonic() > deadline:
                    pytest.fail("modsim did not start")
                time.sleep(0.05)
        yield port
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        process.stderr.close()
    assert process.returncode == 0
