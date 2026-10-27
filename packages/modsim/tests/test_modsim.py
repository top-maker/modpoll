import socket
import signal
import subprocess
import sys
import time

import modsim
import pytest
from pymodbus.client import ModbusTcpClient


@pytest.fixture
def local_tcp_client():
    reservation = socket.socket()
    reservation.bind(("127.0.0.1", 0))
    port = reservation.getsockname()[1]
    reservation.close()

    server = subprocess.Popen(
        [sys.executable, "-m", "modsim", "--port", str(port), "--log", "error"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    client = ModbusTcpClient("127.0.0.1", port=port, timeout=0.5)
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if server.poll() is not None:
                pytest.fail(f"modsim server exited during startup: {server.returncode}")
            if client.connect():
                break
            time.sleep(0.05)
        else:
            pytest.fail("modsim server did not accept a local TCP connection")

        yield client
    finally:
        client.close()
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=5)

    assert server.returncode == 0
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", port))


def test_module_name():
    assert modsim.__name__ == "modsim"


@pytest.mark.integration
def test_local_tcp_server_reads_and_writes_default_holding_registers(local_tcp_client):
    client = local_tcp_client

    result = client.read_holding_registers(40000, count=4, slave=1)
    assert not result.isError()
    assert result.registers == [1, 2, 3, 4]

    result = client.write_registers(40000, [12, 13, 14, 15], slave=1)
    assert not result.isError()
    result = client.read_holding_registers(40000, count=4, slave=1)
    assert not result.isError()
    assert result.registers == [12, 13, 14, 15]


@pytest.mark.integration
def test_local_tcp_server_exercises_all_tables_and_boundaries(local_tcp_client):
    client = local_tcp_client

    coils = client.read_coils(0, count=8, slave=1)
    assert not coils.isError()
    assert coils.bits[:8] == [True, False, True, False, False, False, False, True]

    coil_write = client.write_coil(1, True, slave=1)
    assert not coil_write.isError()
    coil_readback = client.read_coils(0, count=2, slave=1)
    assert not coil_readback.isError()
    assert coil_readback.bits[:2] == [True, True]

    discrete = client.read_discrete_inputs(10000, count=8, slave=1)
    assert not discrete.isError()
    assert discrete.bits[:8] == [
        True,
        False,
        True,
        False,
        False,
        False,
        False,
        True,
    ]

    readonly_coil_write = client.write_coil(10000, True, slave=1)
    assert readonly_coil_write.isError()
    assert client.read_discrete_inputs(10000, count=1, slave=1).bits[0] is True

    last_coil_before = client.read_coils(31, count=1, slave=1)
    assert not last_coil_before.isError()
    assert client.write_coils(31, [True, True], slave=1).isError()
    last_coil_after = client.read_coils(31, count=1, slave=1)
    assert not last_coil_after.isError()
    assert last_coil_after.bits[0] == last_coil_before.bits[0]

    input_registers = client.read_input_registers(30000, count=4, slave=1)
    assert not input_registers.isError()
    assert input_registers.registers == [1, 2, 3, 4]

    readonly_write = client.write_register(30000, 99, slave=1)
    assert readonly_write.isError()
    unchanged = client.read_input_registers(30000, count=1, slave=1)
    assert not unchanged.isError()
    assert unchanged.registers == [1]

    out_of_range = client.read_holding_registers(40043, count=2, slave=1)
    assert out_of_range.isError()
    last_before = client.read_holding_registers(40043, count=1, slave=1)
    assert not last_before.isError()
    out_of_range_write = client.write_registers(40043, [11, 12], slave=1)
    assert out_of_range_write.isError()
    last_after = client.read_holding_registers(40043, count=1, slave=1)
    assert not last_after.isError()
    assert last_after.registers == last_before.registers
    shared_unit = client.read_holding_registers(40000, count=1, slave=42)
    assert not shared_unit.isError()
    assert shared_unit.registers == [1]


def test_import_does_not_parse_cli_arguments():
    result = subprocess.run(
        [sys.executable, "-c", "import modsim.main", "--invalid-option"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0


@pytest.mark.parametrize(
    "arguments",
    [
        ["--store", "sparse"],
        ["--slaves", "1"],
        ["--port", "bad"],
        ["--port", "65536"],
        ["--comm", "tcp", "--framer", "rtu"],
    ],
)
def test_unsupported_cli_options_fail_cleanly(arguments):
    result = subprocess.run(
        [sys.executable, "-m", "modsim"] + arguments,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "error:" in result.stderr
    assert "Traceback" not in result.stderr


@pytest.mark.integration
@pytest.mark.parametrize("sig", [signal.SIGINT, signal.SIGTERM])
def test_signal_shutdown_releases_tcp_port(sig):
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    process = subprocess.Popen(
        [sys.executable, "-m", "modsim", "--port", str(port), "--log", "error"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if process.poll() is not None:
                pytest.fail("server exited during startup")
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                    break
            except OSError:
                time.sleep(0.05)
        else:
            pytest.fail("server did not start")
        process.send_signal(sig)
        assert process.wait(timeout=5) == 0
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", port))
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


@pytest.mark.integration
def test_occupied_tcp_port_fails_promptly():
    with socket.socket() as listener:
        listener.bind(("0.0.0.0", 0))
        listener.listen()
        port = listener.getsockname()[1]
        result = subprocess.run(
            [sys.executable, "-m", "modsim", "--port", str(port), "--log", "error"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    assert result.returncode != 0
    assert "Could not start Modbus TCP listener" in result.stderr


def test_release_version_guard_accepts_matching_tag_and_rejects_mismatch():
    from pathlib import Path

    project = Path(__file__).resolve().parents[1]
    guard = project / ".github/scripts/check-release-version.py"
    for tag, expected in (("v" + modsim.__version__, 0), ("v9.9.9", 1)):
        result = subprocess.run(
            [sys.executable, str(guard), tag],
            cwd=project,
            capture_output=True,
            text=True,
        )
        assert result.returncode == expected
        if expected:
            assert "does not match" in result.stderr


@pytest.mark.integration
def test_local_udp_server_and_shutdown():
    from pymodbus.client import ModbusUdpClient

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "modsim",
            "--comm",
            "udp",
            "--port",
            str(port),
            "--log",
            "error",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    client = ModbusUdpClient("127.0.0.1", port=port, timeout=0.2, retries=0)
    try:
        deadline = time.monotonic() + 10
        result = None
        while time.monotonic() < deadline:
            if process.poll() is not None:
                pytest.fail("UDP server exited during startup")
            try:
                result = client.read_holding_registers(40000, count=2, slave=1)
                if result and not result.isError():
                    break
            except Exception:
                pass
            time.sleep(0.05)
        assert result and not result.isError()
        assert result.registers == [1, 2]
        process.terminate()
        assert process.wait(timeout=5) == 0
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.bind(("127.0.0.1", port))
    finally:
        client.close()
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


@pytest.mark.integration
def test_occupied_udp_port_fails_promptly():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "modsim",
                "--comm",
                "udp",
                "--port",
                str(port),
                "--log",
                "error",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
    assert result.returncode != 0
    assert "Could not start Modbus UDP listener" in result.stderr


@pytest.mark.integration
def test_local_tls_server_with_ephemeral_certificate(tmp_path):
    import os
    import shutil
    import ssl

    openssl = shutil.which("openssl")
    if not openssl:
        pytest.skip("openssl is needed to generate a temporary certificate")
    certdir = tmp_path / "examples" / "certificates"
    certdir.mkdir(parents=True)
    cert = certdir / "pymodbus.crt"
    key = certdir / "pymodbus.key"
    subprocess.run(
        [
            openssl,
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-keyout",
            str(key),
            "-out",
            str(cert),
            "-days",
            "1",
            "-subj",
            "/CN=localhost",
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(__import__("pathlib").Path(__file__).resolve().parents[1])
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "modsim",
            "--comm",
            "tls",
            "--port",
            str(port),
            "--log",
            "error",
        ],
        cwd=tmp_path,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    context = ssl.create_default_context(cafile=str(cert))
    try:
        deadline = time.monotonic() + 10
        while True:
            if process.poll() is not None:
                pytest.fail(
                    "TLS server exited during startup: " + process.stderr.read()
                )
            try:
                raw = socket.create_connection(("127.0.0.1", port), timeout=0.5)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    pytest.fail("TLS server did not start")
                time.sleep(0.05)
        with context.wrap_socket(raw, server_hostname="localhost") as client:
            client.settimeout(2)
            client.sendall(b"\x03\x9c\x40\x00\x02")
            response = b""
            while len(response) < 6:
                part = client.recv(6 - len(response))
                assert part
                response += part
            assert response == b"\x03\x04\x00\x01\x00\x02"
        conflict = subprocess.run(
            [
                sys.executable,
                "-m",
                "modsim",
                "--comm",
                "tls",
                "--port",
                str(port),
                "--log",
                "error",
            ],
            cwd=tmp_path,
            env=env,
            capture_output=True,
            text=True,
            timeout=5,
        )
        assert conflict.returncode != 0
        assert "Could not start Modbus TLS listener" in conflict.stderr
        process.terminate()
        assert process.wait(timeout=5) == 0
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
