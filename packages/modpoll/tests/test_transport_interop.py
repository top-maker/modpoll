"""M3 UDP and POSIX virtual-serial acceptance with independent wire checks."""

import os
from pathlib import Path
import select
import socket
import subprocess
import sys
import threading
import time
import json

import pytest
from pymodbus.client import ModbusSerialClient, ModbusUdpClient
from pymodbus.framer import FramerType

from tools.verify_modsim_equivalence import (
    assert_values,
    EXPECTED_REQUESTS,
    snapshots_match,
)

ROOT = Path(__file__).resolve().parents[1]
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.environ.get("MODSIM_PYTHON")
        or not os.environ.get("MODSIM_SOURCE")
        or not os.environ.get("MODPOLL_1X_SOURCE"),
        reason="requires installed simulator and fixed v1 baseline",
    ),
]


class PtyBridge:
    def __enter__(self):
        import tty

        self.left, self.left_slave = os.openpty()
        self.right, self.right_slave = os.openpty()
        tty.setraw(self.left_slave)
        tty.setraw(self.right_slave)
        self.client_path, self.server_path = os.ttyname(self.left_slave), os.ttyname(
            self.right_slave
        )
        self.stop = threading.Event()
        self.trace = bytearray()
        self.lock = threading.Lock()
        self.worker = threading.Thread(target=self.run, daemon=True)
        self.worker.start()
        return self

    def run(self):
        while not self.stop.is_set():
            ready, _, _ = select.select([self.left, self.right], [], [], 0.05)
            for source in ready:
                try:
                    payload = os.read(source, 4096)
                    if source == self.left:
                        with self.lock:
                            self.trace.extend(payload)
                    os.write(self.right if source == self.left else self.left, payload)
                except OSError:
                    if self.stop.wait(0.01):
                        return

    def reset(self):
        with self.lock:
            self.trace.clear()

    def captured(self):
        with self.lock:
            return bytes(self.trace)

    def __exit__(self, *args):
        self.stop.set()
        self.worker.join(timeout=2)
        for fd in (self.left, self.right, self.left_slave, self.right_slave):
            os.close(fd)


def crc16(data):
    value = 0xFFFF
    for byte in data:
        value ^= byte
        for _ in range(8):
            value = (value >> 1) ^ (0xA001 if value & 1 else 0)
    return value.to_bytes(2, "little")


def expected_serial(framer):
    frames = []
    for unit, fc, address, count in EXPECTED_REQUESTS:
        payload = (
            bytes([unit, fc]) + address.to_bytes(2, "big") + count.to_bytes(2, "big")
        )
        frames.append(
            payload + crc16(payload)
            if framer == "rtu"
            else b":"
            + (payload + bytes([(-sum(payload)) & 255])).hex().upper().encode()
            + b"\r\n"
        )
    return b"".join(frames)


def run_client(source, config, arguments, output):
    # The 2.x client is this checkout, run in the interpreter running the tests: the workspace
    # environment lives at the repository root since TOOL-01. A baseline keeps its own venv.
    python = sys.executable if source == ROOT else str(source / ".venv/bin/python")
    result = subprocess.run(
        [
            python,
            "-m",
            "modpoll",
            "--once",
            "--config",
            str(config),
            "--export",
            str(output),
            "--interval",
            "0",
            "--delay",
            "0",
            "--timeout",
            "1",
            "--loglevel",
            "ERROR",
            *arguments,
        ],
        cwd=source,
        text=True,
        capture_output=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
    assert not result.stderr.strip(), result.stderr
    data = json.loads(output.read_text())
    assert_values(data)
    return data


def start_simulator(comm, port, framer=None):
    command = [
        os.environ["MODSIM_PYTHON"],
        "-m",
        "modsim",
        "--comm",
        comm,
        "--port",
        str(port),
        "--log",
        "error",
    ]
    if framer:
        command += ["--framer", framer]
    return subprocess.Popen(
        command,
        cwd=os.environ["MODSIM_SOURCE"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )


def wait_ready(process, client):
    deadline = time.monotonic() + 10
    try:
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise AssertionError(process.stderr.read().decode())
            try:
                if client.connect():
                    result = client.read_holding_registers(40000, count=1, device_id=1)
                    if not result.isError():
                        return
            except Exception:
                pass
            time.sleep(0.05)
        raise AssertionError("simulator did not become ready")
    finally:
        client.close()


def stop_simulator(process):
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)
    stderr = process.stderr.read().decode()
    process.stderr.close()
    assert process.returncode == 0, stderr


def test_udp_preserves_csv_tm_results(tmp_path):
    with socket.socket(type=socket.SOCK_DGRAM) as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    process = start_simulator("udp", port)
    baseline = Path(os.environ["MODPOLL_1X_SOURCE"])
    try:
        wait_ready(
            process, ModbusUdpClient("127.0.0.1", port=port, timeout=0.2, retries=0)
        )
        results = []
        for label, source, config in [
            ("csv", baseline, baseline / "examples/modsim.csv"),
            ("tm", ROOT, ROOT / "examples/modsim.tm.json"),
        ]:
            results.append(
                run_client(
                    source,
                    config,
                    ["--udp", "127.0.0.1", "--udp-port", str(port)],
                    tmp_path / (label + ".json"),
                )
            )
        assert snapshots_match(results[0], results[1])
    finally:
        stop_simulator(process)


@pytest.mark.skipif(os.name != "posix", reason="requires POSIX virtual terminals")
@pytest.mark.parametrize("framer", ["rtu", "ascii"])
def test_serial_actual_frames_and_values(tmp_path, framer):
    baseline = Path(os.environ["MODPOLL_1X_SOURCE"])
    with PtyBridge() as bridge:
        process = start_simulator("serial", bridge.server_path, framer)
        try:
            wait_ready(
                process,
                ModbusSerialClient(
                    bridge.client_path,
                    framer=FramerType.RTU if framer == "rtu" else FramerType.ASCII,
                    baudrate=19200,
                    timeout=0.2,
                    retries=0,
                ),
            )
            if framer == "rtu":
                bridge.reset()
                point = run_client(
                    baseline,
                    baseline / "examples/modsim.csv",
                    ["--serial", bridge.client_path, "--serial-baud", "19200"],
                    tmp_path / "csv.json",
                )
                assert bridge.captured() == expected_serial("rtu")
            else:
                # The pinned v1 explicit-framer path is broken; do not invent parity.
                result = subprocess.run(
                    [
                        str(baseline / ".venv/bin/python"),
                        "-m",
                        "modpoll",
                        "--once",
                        "--config",
                        str(baseline / "examples/modsim.csv"),
                        "--serial",
                        bridge.client_path,
                        "--framer",
                        "ascii",
                    ],
                    cwd=baseline,
                    text=True,
                    capture_output=True,
                    timeout=10,
                )
                assert (
                    result.returncode != 0 and "Only RTU/ASCII allowed" in result.stderr
                )
                point = None
            bridge.reset()
            result = run_client(
                ROOT,
                ROOT / "examples/modsim.tm.json",
                [
                    "--rtu" if framer == "rtu" else "--serial",
                    bridge.client_path,
                    "--serial-baud",
                    "19200",
                    "--framer",
                    framer,
                ],
                tmp_path / "tm.json",
            )
            if point is not None:
                assert snapshots_match(result, point), (result, point)
            assert bridge.captured() == expected_serial(framer)
        finally:
            stop_simulator(process)
