"""Exercise immutable catalog inputs with independent released clients on loopback."""

import argparse
import copy
import hashlib
from importlib.metadata import version
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
from urllib.request import urlopen

from modpoll_wot import export_td
import yaml

ROOT = Path(__file__).resolve().parents[1]
TM_PATH = "products/advantech/adam-5017uh/models/adam-5017uh.tm.json"
VALUES = [0x1234, 0x8001, 0xABCD, 0, 65535, 42, 0x0102, 0xFE01]
EXPECTED = {f"AI{i}_RAW": value for i, value in enumerate(VALUES)}


def receive(stream, count):
    data = b""
    while len(data) < count:
        part = stream.recv(count - len(data))
        if not part:
            raise ValueError("Incomplete Modbus response")
        data += part
    return data


def node_values(reader, td):
    result = subprocess.run(
        ["node", str(reader), str(td)],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    line = next(
        line for line in result.stdout.splitlines() if line.startswith("RESULT=")
    )
    return json.loads(line[7:])


def run(args):
    lock = yaml.safe_load(args.lock.read_text())
    revision = lock["revision"]
    if len(revision) != 40 or any(c not in "0123456789abcdef" for c in revision):
        raise ValueError("Full immutable data commit required")
    url = f"https://raw.githubusercontent.com/{lock['repository']}/{revision}/{TM_PATH}"
    with urlopen(url, timeout=20) as response:
        payload = response.read(2 * 1024 * 1024 + 1)
    digest = hashlib.sha256(payload).hexdigest()
    if digest != lock["files"][TM_PATH]:
        raise ValueError("Catalog TM hash mismatch")
    reader = args.node_reader.resolve()
    node_versions = {
        name: json.loads(
            (
                reader.parent / "node_modules/@node-wot" / name / "package.json"
            ).read_text()
        )["version"]
        for name in ("core", "binding-modbus")
    }
    if set(node_versions.values()) != {"0.9.2"}:
        raise ValueError("Expected pinned node-wot 0.9.2")
    with socket.socket() as reserve:
        reserve.bind(("127.0.0.1", 0))
        port = reserve.getsockname()[1]
    with TemporaryDirectory(prefix="modsim-catalog-interop-") as temporary:
        work = Path(temporary)
        if args.vectors and json.loads(args.vectors.read_bytes()) != EXPECTED:
            raise ValueError(
                "Catalog vectors differ from the independent expected vector"
            )
        scenario = work / "initial.sim.json"
        scenario.write_text(json.dumps({"version": "1", "initial": EXPECTED}))
        vectors_digest = (
            hashlib.sha256(args.vectors.read_bytes()).hexdigest()
            if args.vectors
            else None
        )
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        with (work / "simulator.log").open("w+") as log:
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "modsim",
                    "--config",
                    url,
                    "--bind",
                    "127.0.0.1",
                    "--port",
                    str(port),
                    "--unit-id",
                    "1",
                    "--scenario",
                    str(scenario),
                ],
                cwd=work,
                env=env,
                stdout=log,
                stderr=log,
            )
            try:
                deadline = time.monotonic() + 30
                while True:
                    if process.poll() is not None:
                        log.seek(0)
                        raise ValueError(log.read())
                    try:
                        stream = socket.create_connection(
                            ("127.0.0.1", port), timeout=1
                        )
                        break
                    except OSError:
                        if time.monotonic() >= deadline:
                            raise TimeoutError("Simulator did not become ready")
                        time.sleep(0.1)
                with stream:
                    stream.sendall(struct.pack(">HHHBBHH", 7, 0, 6, 1, 4, 1, 8))
                    raw_header = receive(stream, 7)
                    raw_body = receive(stream, 18)
                    assert raw_header == struct.pack(">HHHB", 7, 0, 19, 1)
                    assert raw_body == bytes([4, 16]) + struct.pack(">8H", *VALUES)
                output = work / "modpoll.json"
                subprocess.run(
                    [
                        str(args.modpoll_python),
                        "-m",
                        "modpoll",
                        "--once",
                        "--tcp",
                        "127.0.0.1",
                        "--tcp-port",
                        str(port),
                        "--unit-id",
                        "1",
                        "--config",
                        url,
                        "--timeout",
                        "10",
                        "--interval",
                        "0",
                        "--export",
                        str(output),
                    ],
                    cwd=work,
                    env=env,
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=40,
                )
                polled = json.loads(output.read_text())
                assert len(polled) == 1 and next(iter(polled.values())) == EXPECTED
                td = export_td(
                    json.loads(payload),
                    host="127.0.0.1",
                    port=port,
                    unit_id=1,
                    target="node-wot-0.9.2",
                )
                good = work / "correct.td.json"
                good.write_text(json.dumps(td))
                td_digest = hashlib.sha256(good.read_bytes()).hexdigest()
                node_actual = node_values(reader, good)
                assert node_actual == EXPECTED
                wrong = copy.deepcopy(td)
                for prop in wrong["properties"].values():
                    for form in prop["forms"]:
                        form["contentType"] = form["contentType"].replace(
                            "BIG_ENDIAN", "LITTLE_ENDIAN"
                        )
                bad = work / "wrong-byte-order.td.json"
                bad.write_text(json.dumps(wrong))
                incorrect = node_values(reader, bad)
                assert incorrect != EXPECTED and incorrect["AI0_RAW"] == 0x3412
            finally:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
        versions = json.loads(
            subprocess.check_output(
                [
                    str(args.modpoll_python),
                    "-c",
                    "import json,importlib.metadata as m; print(json.dumps({p:m.version(p) for p in ['modpoll','modpoll-wot']}))",
                ],
                cwd=work,
                env=env,
            )
        )
    report = {
        "executed-at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "data-revision": revision,
        "vectors-sha256": vectors_digest,
        "td-sha256": td_digest,
        "td-endpoint": {
            "host": "127.0.0.1",
            "port": port,
            "unit-id": 1,
            "target": "node-wot-0.9.2",
        },
        "actual": {
            "modpoll": next(iter(polled.values())),
            "node-wot": node_actual,
            "wrong-byte-order": incorrect,
            "request-hex": struct.pack(">HHHBBHH", 7, 0, 6, 1, 4, 1, 8).hex(),
            "response-hex": (raw_header + raw_body).hex(),
        },
        "tm-sha256": digest,
        "profile": "0.2",
        "modsim": version("modsim"),
        "simulator-interpreter": version("modpoll-wot"),
        "clients": versions,
        "node-wot": node_versions,
        "reader-sha256": hashlib.sha256(reader.read_bytes()).hexdigest(),
        "checks": {
            "raw-fc4-start-1-count-8": "passed",
            "modpoll": "passed",
            "node-wot": "passed",
            "wrong-byte-order-detected": "passed",
            "shutdown": "passed",
        },
        "expected": EXPECTED,
        "scope": "Synthetic uint16 input subset only; no hardware, calibration, writes or general binding certification",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(
        "Catalog interoperability passed: raw wire, published modpoll, node-wot, wrong-byte-order rejection, shutdown"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--lock", type=Path, default=ROOT / "examples/model-source.yaml"
    )
    parser.add_argument(
        "--vectors",
        type=Path,
        help="Catalog vectors file that must equal the independent known vector",
    )
    parser.add_argument("--modpoll-python", type=Path, required=True)
    parser.add_argument("--node-reader", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Temporary/CI report, outside maintained docs",
    )
    run(parser.parse_args())
