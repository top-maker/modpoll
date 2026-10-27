import socket
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
    out_of_range_write = client.write_registers(40043, [11, 12], slave=1)
    assert out_of_range_write.isError()
