"""Compare installed 1.x CSV and 2.x TM/TD CLIs against one modsim process.

This is a read-only test. Supply isolated installations of both projects.
The proxy records Modbus requests, so equal output cannot hide smaller reads.
"""

import argparse
import json
import math
from pathlib import Path
import socket
import socketserver
import struct
import subprocess
import tempfile
import threading
import time


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_REQUESTS = [
    (1, 1, 0, 16),
    (1, 2, 10000, 16),
    (1, 4, 30000, 20),
    (1, 3, 40000, 44),
]


def recv_exact(sock, length):
    data = b""
    while len(data) < length:
        chunk = sock.recv(length - len(data))
        if not chunk:
            raise EOFError("connection closed")
        data += chunk
    return data


def frame(sock):
    header = recv_exact(sock, 7)
    return header + recv_exact(sock, int.from_bytes(header[4:6], "big") - 1)


class Proxy(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


class Handler(socketserver.BaseRequestHandler):
    def handle(self):
        self.request.settimeout(5)
        try:
            with socket.create_connection(self.server.upstream, timeout=5) as upstream:
                while True:
                    request = frame(self.request)
                    if len(request) != 12:
                        raise ValueError("unexpected request length")
                    self.server.requests.append(
                        (
                            request[6],
                            request[7],
                            int.from_bytes(request[8:10], "big"),
                            int.from_bytes(request[10:12], "big"),
                        )
                    )
                    upstream.sendall(request)
                    self.request.sendall(frame(upstream))
        except EOFError:
            pass
        except Exception as exc:
            self.server.errors.append(str(exc))


def assert_values(snapshot):
    data = snapshot["modsim01"]
    assert len(data) == 37, data
    bits = [True, False, True, False, False, False, False, True]
    for name in ("coil01-08", "coil09-16", "di01-08", "di09-16"):
        assert data[name] == bits, (name, data[name])
    values = [
        1,
        2,
        3,
        4,
        -1,
        -2,
        -3,
        -4,
        12345678,
        12345.678,
        -12345678,
        -12345678000.0,
        12.34,
        -12.34,
    ]
    for prefix in ("input_reg", "holding_reg"):
        for index, value in enumerate(values, 1):
            actual = data[f"{prefix}{index:02}"]
            assert actual is not None and math.isclose(actual, value, rel_tol=1e-6), (
                index,
                actual,
                value,
            )
    for index, value in enumerate(
        (12345678900, -12345678900, 123.45, -123.45, "this is a string"), 15
    ):
        assert data[f"holding_reg{index:02}"] == value


def table_cells(text):
    """Compare terminal tables by cell values; 1.x says Reference where 2.x says Point."""
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("+"):
            continue
        if line.startswith("|"):
            cells = tuple(cell.strip() for cell in line.strip("|").split("|"))
            if cells[0] not in ("Reference", "Point"):
                rows.append(cells)
        elif line:
            rows.append(line)
    return rows


def same_value(left, right):
    """Whether two numbers or strings name the same value.

    1.x and 2.x render one reading with different precision, so the text of
    a float may differ while the value it names stays the same.
    """
    if isinstance(left, bool) or isinstance(right, bool):
        return left is right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return _same_float(float(left), float(right))
    if left == right:
        return True
    return _same_number(left, right)


def _same_number(left, right):
    """Whether two texts both name a number and name the same one."""
    try:
        left_number = float(left)
        right_number = float(right)
    except (TypeError, ValueError):
        return False
    if math.isnan(left_number) or math.isnan(right_number):
        return False
    return _same_float(left_number, right_number)


def _same_float(left, right):
    """Whether two floats name the same reading.

    A float32 register is shown as its shortest decimal in 2.x (12.34) and as
    the double it widens to in 1.x (12.34000015258789). Both name one float32.
    """
    if math.isclose(left, right, rel_tol=1e-9, abs_tol=1e-12):
        return True
    return _to_float32(left) == right or _to_float32(right) == left


def _to_float32(value):
    try:
        return struct.unpack("<f", struct.pack("<f", value))[0]
    except (OverflowError, struct.error):
        return None


def snapshots_match(left, right):
    """Whether two snapshots name the same values, whatever their float text."""
    if set(left) != set(right):
        return False
    return all(
        (
            snapshots_match(left[key], right[key])
            if isinstance(left[key], dict) and isinstance(right[key], dict)
            else same_value(left[key], right[key])
        )
        for key in left
    )


def tables_match(left, right):
    """Whether two terminal tables show the same values, whatever their text."""
    if len(left) != len(right):
        return False
    for left_row, right_row in zip(left, right):
        if len(left_row) != len(right_row):
            return False
        if not all(same_value(a, b) for a, b in zip(left_row, right_row)):
            return False
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--modpoll-1x", type=Path, required=True)
    parser.add_argument("--modsim", type=Path)
    parser.add_argument("--remote-host")
    parser.add_argument("--remote-port", type=int, default=502)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    old = args.modpoll_1x.resolve()
    server = None
    host = args.remote_host or "127.0.0.1"
    if args.remote_host:
        port = args.remote_port
    else:
        if args.modsim is None:
            parser.error("--modsim is required for a local simulator")
        simulator = args.modsim.resolve()
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        server = subprocess.Popen(
            [
                str(simulator / ".venv/bin/python"),
                "-m",
                "modsim",
                "--port",
                str(port),
                "--log",
                "error",
            ],
            cwd=simulator,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
    runs = []
    try:
        deadline = time.monotonic() + 10
        while True:
            if server is not None and server.poll() is not None:
                raise RuntimeError(server.stderr.read().decode())
            try:
                with socket.create_connection((host, port), timeout=1):
                    break
            except OSError:
                if time.monotonic() > deadline:
                    raise TimeoutError("modsim did not start")
                time.sleep(0.05)
        with tempfile.TemporaryDirectory() as temp:
            for label, root, config in (
                ("1.x CSV", old, old / "examples/modsim.csv"),
                ("2.x TM", ROOT, ROOT / "examples/modsim.tm.json"),
                ("2.x TD", ROOT, ROOT / "examples/modsim.generated.td.json"),
            ):
                with Proxy(("127.0.0.1", 0), Handler) as proxy:
                    proxy.upstream = (host, port)
                    proxy.requests, proxy.errors = [], []
                    worker = threading.Thread(target=proxy.serve_forever, daemon=True)
                    worker.start()
                    output = Path(temp) / "values.json"
                    command = [
                        str(root / ".venv/bin/python"),
                        "-m",
                        "modpoll",
                        "--once",
                        "--tcp",
                        "127.0.0.1",
                        "--tcp-port",
                        str(proxy.server_address[1]),
                        "--config",
                        str(config),
                        "--export",
                        str(output),
                        "--interval",
                        "0",
                        "--delay",
                        "0",
                        "--loglevel",
                        "ERROR",
                    ]
                    try:
                        result = subprocess.run(
                            command,
                            cwd=root,
                            text=True,
                            capture_output=True,
                            timeout=20,
                        )
                        assert result.returncode == 0, result.stderr
                        assert not result.stderr.strip(), result.stderr
                        snapshot = json.loads(output.read_text())
                        if args.remote_host:
                            assert len(snapshot["modsim01"]) == 37
                            assert all(
                                value is not None
                                for value in snapshot["modsim01"].values()
                            )
                        else:
                            assert_values(snapshot)
                        assert proxy.requests == EXPECTED_REQUESTS, proxy.requests
                        assert not proxy.errors, proxy.errors
                        runs.append(
                            {
                                "label": label,
                                "snapshot": snapshot,
                                "requests": list(proxy.requests),
                                "table": table_cells(
                                    result.stdout[result.stdout.index("Device:") :]
                                ),
                            }
                        )
                    finally:
                        proxy.shutdown()
                        worker.join(timeout=5)
        assert all(
            snapshots_match(run["snapshot"], runs[0]["snapshot"]) for run in runs
        )
        assert all(tables_match(run["table"], runs[0]["table"]) for run in runs)
        report = {
            "upstream": host,
            "fixed_initial_values_verified": not bool(args.remote_host),
            "success": True,
            "properties": 37,
            "requests_per_cycle": 4,
            "runs": runs,
        }
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n")
        print(
            "PASS: 1.x CSV = 2.x TM = 2.x TD; 37 values, terminal tables and 4 block requests match"
        )
    finally:
        if server is not None:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)
            server.stderr.close()


if __name__ == "__main__":
    main()
