"""Opt-in MQTT integration against a disposable local Mosquitto container.

Run with MODPOLL_MQTT_INTEGRATION=1 and Docker access. The container publishes
only on loopback, uses a temporary password file, and is removed at teardown.
"""

import os
import queue
import socket
import subprocess
import time

import pytest
from paho.mqtt.client import CallbackAPIVersion, Client, MQTTProtocolVersion

from modpoll.main import process_mqtt_command
from modpoll.mqtt_task import MqttHandler

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("MODPOLL_MQTT_INTEGRATION") != "1",
        reason="requires local Docker broker",
    ),
]
IMAGE = "eclipse-mosquitto:2"


def docker(*args):
    return subprocess.run(
        ["docker", *args], check=True, text=True, capture_output=True
    ).stdout.strip()


def wait_for(predicate, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = predicate()
        if result:
            return result
        time.sleep(0.05)
    raise AssertionError("Timed out waiting for broker state")


@pytest.fixture
def broker(tmp_path):
    tmp_path.chmod(0o755)
    password_dir = tmp_path / "broker"
    password_dir.mkdir(mode=0o777)
    password_dir.chmod(0o777)
    docker(
        "run",
        "--rm",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "-v",
        f"{password_dir}:/work",
        "--entrypoint",
        "mosquitto_passwd",
        IMAGE,
        "-b",
        "-c",
        "/work/passwords",
        "tester",
        "secret",
    )
    (password_dir / "passwords").chmod(0o644)
    (password_dir / "mosquitto.conf").write_text(
        "listener 1883 0.0.0.0\nallow_anonymous false\npassword_file /mosquitto/config/passwords\npersistence false\n"
    )
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    container = docker(
        "run",
        "-d",
        "-p",
        f"127.0.0.1:{port}:1883",
        "-v",
        f"{password_dir}:/mosquitto/config:ro",
        IMAGE,
    )
    try:
        endpoint = docker("port", container, "1883/tcp")
        port = int(endpoint.rsplit(":", 1)[1])
        yield container, port
    finally:
        subprocess.run(["docker", "rm", "-f", container], capture_output=True)


def handler(port, version="3.1.1", password="secret"):
    result = MqttHandler(
        "test",
        "127.0.0.1",
        port,
        "tester",
        password,
        None,
        0,
        subscribe_topics=["modpoll/+/set"],
        mqtt_version=version,
    )
    assert result.setup()
    return result


def publisher(port, version):
    protocol = (
        MQTTProtocolVersion.MQTTv5 if version == "5.0" else MQTTProtocolVersion.MQTTv311
    )
    client = Client(CallbackAPIVersion.VERSION2, protocol=protocol)
    client.username_pw_set("tester", "secret")
    client.connect("127.0.0.1", port)
    client.loop_start()
    wait_for(client.is_connected)
    return client


def receive(handler):
    value = handler.receive()
    return value if value[0] else None


@pytest.mark.parametrize("version", ["3.1.1", "5.0"])
def test_retained_command_is_rejected_and_reconnect_restores_subscription(
    broker, version
):
    container, port = broker
    pub = publisher(port, version)
    poller = handler(port, version)
    try:
        pub.publish(
            "modpoll/meter/set",
            '{"object_type":"coil","address":1,"value":1}',
            retain=True,
        ).wait_for_publish()
        assert poller.connect()
        topic, payload, retained = wait_for(lambda: receive(poller))
        assert retained is True
        assert (
            process_mqtt_command(topic, payload, retained, "modpoll/+/set", []) is False
        )
        pub.publish("modpoll/meter/set", b"", retain=True).wait_for_publish()
        # Discard the live deletion notification before the reconnect check.
        assert wait_for(lambda: receive(poller)) == ("modpoll/meter/set", b"", False)
        docker("stop", "--time", "0", container)
        wait_for(lambda: not poller.is_connected())
        wait_for(lambda: not pub.is_connected())
        docker("start", container)
        wait_for(poller.is_connected, timeout=25)
        # Publisher also uses Paho automatic reconnection.
        wait_for(pub.is_connected, timeout=25)
        time.sleep(0.2)
        pub.publish("modpoll/meter/set", b"after-reconnect").wait_for_publish()
        assert wait_for(lambda: receive(poller)) == (
            "modpoll/meter/set",
            b"after-reconnect",
            False,
        )
    finally:
        poller.close()
        pub.disconnect()
        pub.loop_stop()


def test_authentication_rejection_and_queue_full(broker, caplog):
    _, port = broker
    rejected = handler(port, password="wrong")
    try:
        assert rejected.connect() is False
        assert not rejected.is_connected()
    finally:
        rejected.close()
    bounded = handler(port)
    bounded.rx_queue = queue.Queue(maxsize=1)
    message = type(
        "Message", (), {"topic": "modpoll/meter/set", "payload": b"{}", "retain": 0}
    )()
    bounded._on_message(None, None, message)
    bounded._on_message(None, None, message)
    assert bounded.rx_queue.qsize() == 1
    assert "queue is full" in caplog.text
