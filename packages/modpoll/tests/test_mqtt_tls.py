"""Private TLS broker, QoS2 CLI output/commands and certificate failure cases."""

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import uuid

import pytest

from modpoll.mqtt_task import MqttHandler
from tests.test_mqtt_modsim_interop import Observer, telemetry, rounded_values, wait_for
from tools.verify_modsim_equivalence import assert_values

ROOT = Path(__file__).resolve().parents[1]
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("MODPOLL_MQTT_INTEGRATION") != "1",
        reason="requires explicit local Docker broker tests",
    ),
]


def command(*args):
    return subprocess.run(
        args, check=True, text=True, capture_output=True
    ).stdout.strip()


@pytest.fixture(scope="module")
def tls_broker(tmp_path_factory):
    root = tmp_path_factory.mktemp("mqtt-tls")
    root.chmod(0o755)
    certs = root / "broker"
    certs.mkdir(mode=0o755)
    ca = root / "ca.crt"
    bad = root / "untrusted.crt"
    for name, certificate in [("ca", ca), ("untrusted", bad)]:
        command(
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "1",
            "-keyout",
            str(root / (name + ".key")),
            "-out",
            str(certificate),
            "-subj",
            "/CN=" + name,
            "-addext",
            "basicConstraints=critical,CA:TRUE",
            "-addext",
            "keyUsage=critical,keyCertSign,cRLSign",
        )
    command(
        "openssl",
        "req",
        "-newkey",
        "rsa:2048",
        "-nodes",
        "-keyout",
        str(certs / "server.key"),
        "-out",
        str(root / "server.csr"),
        "-subj",
        "/CN=localhost",
    )
    (root / "server.ext").write_text(
        "basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\nsubjectAltName=DNS:localhost\n"
    )
    command(
        "openssl",
        "x509",
        "-req",
        "-in",
        str(root / "server.csr"),
        "-CA",
        str(ca),
        "-CAkey",
        str(root / "ca.key"),
        "-CAcreateserial",
        "-out",
        str(certs / "server.crt"),
        "-days",
        "1",
        "-extfile",
        str(root / "server.ext"),
    )
    (certs / "ca.crt").write_bytes(ca.read_bytes())
    (certs / "server.key").chmod(
        0o644
    )  # Disposable test key, readable by container UID.
    command(
        "docker",
        "run",
        "--rm",
        "--user",
        str(os.getuid()),
        "-v",
        str(certs) + ":/work",
        "--entrypoint",
        "mosquitto_passwd",
        "eclipse-mosquitto:2",
        "-b",
        "-c",
        "/work/passwords",
        "tester",
        "secret",
    )
    (certs / "passwords").chmod(0o644)
    (certs / "mosquitto.conf").write_text(
        "listener 1883\nallow_anonymous false\npassword_file /mosquitto/config/passwords\ncafile /mosquitto/config/ca.crt\ncertfile /mosquitto/config/server.crt\nkeyfile /mosquitto/config/server.key\ntls_version tlsv1.2\npersistence false\n"
    )
    container = command(
        "docker",
        "run",
        "--rm",
        "-d",
        "-p",
        "127.0.0.1::1883",
        "-v",
        str(certs) + ":/mosquitto/config:ro",
        "eclipse-mosquitto:2",
    )
    try:
        port = int(command("docker", "port", container, "1883/tcp").rsplit(":", 1)[1])
        deadline = time.monotonic() + 10
        while True:
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                    break
            except OSError:
                if time.monotonic() > deadline:
                    raise AssertionError(command("docker", "logs", container))
                time.sleep(0.05)
        yield port, ca, bad
    finally:
        subprocess.run(["docker", "rm", "-f", container], capture_output=True)


@pytest.mark.parametrize("version", ["3.1.1", "5.0"])
@pytest.mark.parametrize("single", [False, True], ids=["grouped", "single"])
def test_tls_qos2_cli_output_and_command_round_trip(
    tls_broker, live_modsim, tmp_path, monkeypatch, version, single
):
    port, ca, _ = tls_broker
    monkeypatch.setenv("MODPOLL_MQTT_HOST", "localhost")
    monkeypatch.setenv("MODPOLL_MQTT_PORT", str(port))
    namespace = "modpoll-tests/" + uuid.uuid4().hex
    observer = Observer(namespace, version, qos=2)
    observer.client.tls_set(ca_certs=str(ca))
    observer.client.username_pw_set("tester", "secret")
    process = None
    try:
        observer.start()
        output = tmp_path / "snapshot.json"
        kind = "tm" if version == "3.1.1" else "td"
        argv = [
            sys.executable,
            "-m",
            "modpoll",
            "--daemon",
            "--config",
            str(
                ROOT
                / "examples"
                / ("modsim.tm.json" if kind == "tm" else "modsim.generated.td.json")
            ),
            "--tcp",
            "127.0.0.1",
            "--tcp-port",
            str(live_modsim),
            "--rate",
            ".5",
            "--interval",
            "0",
            "--delay",
            "0",
            "--export",
            str(output),
            "--mqtt-host",
            "localhost",
            "--mqtt-port",
            str(port),
            "--mqtt-version",
            version,
            "--mqtt-qos",
            "2",
            "--mqtt-clientid",
            uuid.uuid4().hex,
            "--mqtt-use-tls",
            "--mqtt-cacerts",
            str(ca),
            "--mqtt-user",
            "tester",
            "--mqtt-pass",
            "secret",
            "--mqtt-publish-topic-pattern",
            namespace + "/{{device_name}}/data",
            "--mqtt-subscribe-topic-pattern",
            namespace + "/+/set",
            "--loglevel",
            "ERROR",
        ]
        if single:
            argv.append("--mqtt-single")
        process = subprocess.Popen(
            argv, cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
        )
        data = wait_for(lambda: telemetry(observer, namespace, single))
        wait_for(output.exists)
        snapshot = json.loads(output.read_text())
        assert_values(snapshot)
        assert data == rounded_values(snapshot["modsim01"])
        for topic, (_, retained, qos) in observer.snapshot()[0].items():
            if "/data" in topic:
                assert not retained and qos == 2
        observer.publish(
            namespace + "/modsim01/set",
            json.dumps(
                {"object_type": "holding_register", "address": 40000, "value": 432}
            ),
        )
        wait_for(lambda: telemetry(observer, namespace, single)["holding_reg01"] == 432)
    finally:
        if process:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            stderr = process.stderr.read().decode()
            process.stderr.close()
            assert process.returncode == 0, stderr
        observer.close()


@pytest.mark.parametrize("case", ["unknown-ca", "wrong-hostname", "wrong-password"])
def test_tls_and_authentication_fail_closed(tls_broker, case):
    port, ca, bad = tls_broker
    handler = MqttHandler(
        "negative",
        "127.0.0.1" if case == "wrong-hostname" else "localhost",
        port,
        "tester",
        "wrong" if case == "wrong-password" else "secret",
        uuid.uuid4().hex,
        2,
        use_tls=True,
        cacerts=str(bad if case == "unknown-ca" else ca),
        mqtt_version="5.0",
    )
    try:
        assert handler.setup()
        assert not handler.connect()
        assert not handler.is_connected()
    finally:
        handler.close()


def test_explicit_insecure_option_preserves_legacy_behavior(tls_broker):
    port, _, bad = tls_broker
    handler = MqttHandler(
        "insecure-test",
        "127.0.0.1",
        port,
        "tester",
        "secret",
        uuid.uuid4().hex,
        0,
        use_tls=True,
        cacerts=str(bad),
        insecure=True,
        mqtt_version="3.1.1",
    )
    try:
        assert handler.setup() and handler.connect()
    finally:
        handler.close()
