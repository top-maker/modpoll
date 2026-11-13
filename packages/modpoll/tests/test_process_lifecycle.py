from tests.wot_helpers import write_meter

"""Process-level Modbus TCP lifecycle coverage without external services."""

import signal
import socketserver
import subprocess
import sys
import threading

import pytest


class FakeModbusServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


class Handler(socketserver.BaseRequestHandler):
    def handle(self):
        while True:
            data = self.request.recv(1024)
            if not data:
                return
            # The tests issue one FC3 request of one register per connection.
            if len(data) >= 12 and data[7] == 3:
                response = data[:4] + b"\x00\x05" + data[6:8] + b"\x02\x00\x2a"
                self.request.sendall(response)
                self.server.polled.set()


@pytest.mark.integration
@pytest.mark.parametrize("sig", [signal.SIGINT, signal.SIGTERM])
def test_process_exits_promptly_after_successful_poll(tmp_path, sig):
    config = write_meter(tmp_path / "meter.tm.json")
    with FakeModbusServer(("127.0.0.1", 0), Handler) as server:
        server.polled = threading.Event()
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "modpoll",
                "--config",
                str(config),
                "--tcp",
                "127.0.0.1",
                "--tcp-port",
                str(server.server_address[1]),
                "--daemon",
                "--interval",
                "0",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            assert server.polled.wait(10), "polling did not start"
            process.send_signal(sig)
            assert process.wait(timeout=5) == 0
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
            server.shutdown()
            thread.join(timeout=5)


@pytest.mark.integration
def test_invalid_configuration_exits_nonzero(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "modpoll",
            "--config",
            str(tmp_path / "missing.tm.json"),
            "--tcp",
            "127.0.0.1",
        ],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode != 0
    assert "No Modbus config" in result.stderr
