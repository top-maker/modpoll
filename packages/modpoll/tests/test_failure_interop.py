"""Actual failure/recovery and one-shot exit status acceptance."""

import json
from pathlib import Path
import socket
import socketserver
import subprocess
import sys
import threading

import pytest
from pymodbus.client import ModbusTcpClient

from modpoll.arg_parser import get_parser
from modpoll.modbus_task import setup_modbus_handlers
from modpoll.mqtt_task import MqttHandler
from tests.wot_helpers import write_meter
from tests.test_transport_interop import start_simulator, stop_simulator, wait_ready

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.integration


def cli(path, port, output):
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "modpoll",
            "--once",
            "--daemon",
            "--tcp",
            "127.0.0.1",
            "--tcp-port",
            str(port),
            "--config",
            str(path),
            "--export",
            str(output),
            "--interval",
            "0",
            "--delay",
            "0",
            "--timeout",
            ".2",
            "--loglevel",
            "ERROR",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=10,
    )


def test_once_failed_connection_returns_nonzero(tmp_path):
    config = write_meter(tmp_path / "meter.tm.json", start=40000)
    with socket.socket() as reserved:
        reserved.bind(("127.0.0.1", 0))
        output = tmp_path / "failed.json"
        result = cli(config, reserved.getsockname()[1], output)
    assert result.returncode != 0, result.stderr
    assert json.loads(output.read_text()) == {"meter": {"value": None}}


def test_once_export_failure_returns_nonzero(live_modsim, tmp_path):
    config = write_meter(tmp_path / "meter.tm.json", start=40000)
    result = cli(config, live_modsim, tmp_path / "missing" / "snapshot.json")
    assert result.returncode != 0, result.stderr
    assert "Error exporting data" in result.stderr


def test_device_stop_and_restart_resets_quality_and_counts(live_modsim, tmp_path):
    # The fixture establishes that the requested simulator environment is available;
    # this additional process is owned by this test so its lifecycle can be controlled.
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    process = start_simulator("tcp", port)
    handlers = []
    try:
        wait_ready(
            process, ModbusTcpClient("127.0.0.1", port=port, timeout=0.2, retries=0)
        )
        config = write_meter(tmp_path / "meter.tm.json", start=40000)
        args = get_parser().parse_args(
            [
                "--config",
                str(config),
                "--tcp",
                "127.0.0.1",
                "--tcp-port",
                str(port),
                "--daemon",
                "--interval",
                "0",
                "--timeout",
                ".2",
            ]
        )
        handlers = setup_modbus_handlers(args)
        (handler,) = handlers
        (device,) = handler.deviceList
        handler.poll()
        assert device.points["value"].val == 1 and device.pollSuccess
        stop_simulator(process)
        process = None
        handler.poll()
        assert (device.pollCount, device.errorCount, device.pollSuccess) == (
            2,
            1,
            False,
        )
        output = tmp_path / "snapshot.json"
        assert handler.export(output)
        assert json.loads(output.read_text()) == {"meter": {"value": None}}
        process = start_simulator("tcp", port)
        wait_ready(
            process, ModbusTcpClient("127.0.0.1", port=port, timeout=0.2, retries=0)
        )
        handler.poll()
        assert (device.pollCount, device.errorCount, device.pollSuccess) == (3, 1, True)
        assert (
            device.points["value"].val == 1 and device.points["value"].valid_this_poll
        )
    finally:
        for handler in handlers:
            handler.close()
        if process is not None:
            stop_simulator(process)


class NoAckBroker(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


class NoAckHandler(socketserver.BaseRequestHandler):
    def handle(self):
        def packet():
            first = self.request.recv(1)
            if not first:
                return None
            size = 0
            shift = 0
            while True:
                byte = self.request.recv(1)[0]
                size += (byte & 127) << shift
                shift += 7
                if not byte & 128:
                    break
            data = b""
            while len(data) < size:
                data += self.request.recv(size - len(data))
            return first[0], data

        packet()  # CONNECT
        self.request.sendall(b"\x20\x02\x00\x00")
        message = packet()
        if message and message[0] >> 4 == 3:
            self.server.published.set()
        self.server.release.wait(5)  # Intentionally never PUBACK the publication.


def test_mqtt_shutdown_is_bounded_when_puback_is_missing():
    with NoAckBroker(("127.0.0.1", 0), NoAckHandler) as broker:
        broker.published, broker.release = threading.Event(), threading.Event()
        server = threading.Thread(target=broker.serve_forever, daemon=True)
        server.start()
        handler = MqttHandler(
            "bounded",
            "127.0.0.1",
            broker.server_address[1],
            None,
            None,
            "bounded-test",
            1,
            mqtt_version="3.1.1",
        )
        handler.close_timeout = 0.2
        done = threading.Event()
        worker = None
        try:
            assert handler.setup() and handler.connect()
            infos = [handler.publish("test/bounded", "data") for _ in range(1001)]
            assert infos[-1].rc != 0, "outbound queue did not enforce its limit"
            assert len(handler._pending_publishes) == 1000
            assert broker.published.wait(2)

            def close():
                handler.close()
                done.set()

            worker = threading.Thread(target=close, daemon=True)
            worker.start()
            finished = done.wait(1.5)
        finally:
            broker.release.set()
            if worker:
                worker.join(timeout=3)
            else:
                handler.close()
            broker.shutdown()
            server.join(timeout=2)
        assert finished, "MQTT close waited indefinitely for a missing PUBACK"
        assert handler.unpublished_count == 1000
