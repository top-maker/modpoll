"""Opt-in real MQTT/CLI equivalence and command tests on private UUID topics.

Set MODPOLL_MQTT_HOST (e.g. broker.emqx.io), MODSIM_PYTHON, MODSIM_SOURCE,
and MODPOLL_1X_SOURCE. No other topics are subscribed to or changed. Writes
only target the temporary local simulator. The retained test key is cleared.
"""

import json
import os
from pathlib import Path
import sys
import subprocess
import threading
import time
import uuid

import pytest
from paho.mqtt.client import CallbackAPIVersion, Client, MQTTProtocolVersion
from pymodbus.client import ModbusTcpClient

ROOT = Path(__file__).resolve().parents[1]
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.environ.get("MODPOLL_MQTT_HOST")
        or not os.environ.get("MODPOLL_1X_SOURCE"),
        reason="requires explicit broker and 1.x baseline environment",
    ),
]


def wait_for(predicate, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.05)
    raise AssertionError("Timed out waiting for MQTT/Modbus result")


class Observer:
    def __init__(self, root, version, qos=1):
        self.root, self.messages, self.lock = root, {}, threading.Lock()
        self.count = 0
        self.qos = qos
        self.connected, self.subscribed = threading.Event(), threading.Event()
        self.client = Client(
            CallbackAPIVersion.VERSION2,
            client_id="observer-" + uuid.uuid4().hex,
            protocol=(
                MQTTProtocolVersion.MQTTv5
                if version == "5.0"
                else MQTTProtocolVersion.MQTTv311
            ),
        )
        self.client.on_connect = self.on_connect
        self.client.on_subscribe = lambda *args: self.subscribed.set()
        self.client.on_message = self.on_message

    def on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            self.connected.set()
            client.subscribe(self.root + "/#", qos=self.qos)

    def on_message(self, client, userdata, message):
        with self.lock:
            self.messages[message.topic] = (
                bytes(message.payload),
                message.retain,
                message.qos,
            )
            if "/data" in message.topic:
                self.count += 1

    def start(self):
        self.client.connect(
            os.environ["MODPOLL_MQTT_HOST"],
            int(os.environ.get("MODPOLL_MQTT_PORT", "1883")),
            keepalive=30,
        )
        self.client.loop_start()
        assert self.connected.wait(15), "MQTT CONNACK failed"
        assert self.subscribed.wait(15), "MQTT SUBACK failed"
        return self

    def publish(self, topic, payload, retain=False):
        info = self.client.publish(topic, payload, qos=self.qos, retain=retain)
        info.wait_for_publish(timeout=15)
        assert info.is_published(), "MQTT publication not acknowledged"

    def snapshot(self):
        with self.lock:
            return dict(self.messages), self.count

    def close(self):
        self.client.disconnect()
        self.client.loop_stop()


def scalar(payload):
    if payload == b"True":
        return True
    if payload == b"False":
        return False
    try:
        return json.loads(payload)
    except ValueError:
        return payload.decode()


def telemetry(observer, prefix, single):
    messages, _ = observer.snapshot()
    base = prefix + "/modsim01/data"
    if not single:
        if base not in messages:
            return None
        return json.loads(messages[base][0])
    model = json.loads((ROOT / "examples/modsim.tm.json").read_text())
    result = {}
    for name, prop in model["properties"].items():
        topic = base + "/" + name
        if prop["type"] == "array":
            topics = [topic + "/" + str(i) for i in range(8)]
            if any(t not in messages for t in topics):
                return None
            result[name] = [scalar(messages[t][0]) for t in topics]
        else:
            if topic not in messages:
                return None
            result[name] = scalar(messages[topic][0])
    return result


def rounded_values(snapshot):
    return {
        key: round(value, 3) if isinstance(value, float) else value
        for key, value in snapshot.items()
        if key != "timestamp"
    }


@pytest.mark.parametrize(
    "version,single,qos",
    [
        ("3.1.1", False, 0),
        ("5.0", False, 0),
        ("3.1.1", False, 1),
        ("5.0", False, 1),
        ("3.1.1", True, 1),
        ("5.0", True, 1),
    ],
    ids=[
        "grouped-json-3.1.1-qos0",
        "grouped-json-5.0-qos0",
        "grouped-json-3.1.1-qos1",
        "grouped-json-5.0-qos1",
        "individual-topics-3.1.1-qos1",
        "individual-topics-5.0-qos1",
    ],
)
def test_csv_tm_td_mqtt_equivalence_and_local_write_commands(
    live_modsim, tmp_path, version, single, qos
):
    namespace = "modpoll-tests/" + uuid.uuid4().hex
    observer = Observer(namespace, version)
    baseline = Path(os.environ["MODPOLL_1X_SOURCE"]).resolve()
    runs = [
        ("csv", baseline, baseline / "examples/modsim.csv"),
        ("tm", ROOT, ROOT / "examples/modsim.tm.json"),
        ("td", ROOT, ROOT / "examples/modsim.generated.td.json"),
    ]
    expected = None
    retained_topics = []
    try:
        observer.start()
        for label, source, config in runs:
            prefix = namespace + "/" + label
            command_topic = prefix + "/modsim01/set"
            retained_topics.append(command_topic)
            # Only the dedicated local simulator is addressed by these commands.
            observer.publish(
                command_topic,
                json.dumps(
                    {"object_type": "holding_register", "address": 40000, "value": 999}
                ),
                retain=True,
            )
            output = tmp_path / (label + ".json")
            command = [
                str(source / ".venv/bin/python"),
                "-m",
                "modpoll",
                "--daemon",
                "--tcp",
                "127.0.0.1",
                "--tcp-port",
                str(live_modsim),
                "--config",
                str(config),
                "--export",
                str(output),
                "--timestamp",
                "--rate",
                "2.0" if single else "0.4",
                "--interval",
                "0",
                "--delay",
                "0",
                "--mqtt-host",
                os.environ["MODPOLL_MQTT_HOST"],
                "--mqtt-port",
                os.environ.get("MODPOLL_MQTT_PORT", "1883"),
                "--mqtt-version",
                version,
                "--mqtt-qos",
                str(qos),
                "--mqtt-clientid",
                "poller-" + uuid.uuid4().hex,
                "--mqtt-publish-topic-pattern",
                prefix + "/{{device_name}}/data",
                "--mqtt-subscribe-topic-pattern",
                prefix + "/+/set",
                "--mqtt-diagnostics-topic-pattern",
                prefix + "/{{device_name}}/diagnostics",
                "--diagnostics-rate",
                "0.4",
                "--loglevel",
                "ERROR",
            ]
            if single:
                command.append("--mqtt-single")
            started = time.time()
            process = subprocess.Popen(
                command, cwd=source, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
            )
            try:

                def ready():
                    if process.poll() is not None:
                        raise AssertionError(process.stderr.read().decode())
                    data = telemetry(observer, prefix, single)
                    return data if data and output.exists() else None

                try:
                    data = wait_for(ready)
                except AssertionError as exc:
                    seen, _ = observer.snapshot()
                    details = [
                        topic[len(prefix) :]
                        for topic in seen
                        if topic.startswith(prefix)
                    ]
                    raise AssertionError(
                        f"{label}: telemetry incomplete; observed {details}"
                    ) from exc
                snapshot = json.loads(output.read_text())["modsim01"]
                assert isinstance(snapshot["timestamp"], (int, float))
                assert started - 1 <= snapshot["timestamp"] <= time.time() + 1
                if not single:
                    assert isinstance(data.pop("timestamp"), (int, float))
                snapshot_values = {
                    key: value for key, value in snapshot.items() if key != "timestamp"
                }
                if source == baseline:
                    # 1.x rounds the payload but writes the raw value to the snapshot.
                    assert data == rounded_values(snapshot)
                else:
                    # 2.x renders the payload and the snapshot with one rule.
                    assert data == snapshot_values
                assert len(data) == 37
                assert (
                    data["holding_reg01"] == 1
                ), "retained command changed local device"
                if expected is None:
                    expected = dict(data)
                # 1.x cannot show more than three decimals, so the versions are
                # compared at the resolution 1.x offers.
                assert rounded_values(data) == rounded_values(expected)
                diag_topic = prefix + "/modsim01/diagnostics"
                diagnostic = wait_for(lambda: observer.snapshot()[0].get(diag_topic))
                diagnostic = json.loads(diagnostic[0])
                assert (
                    diagnostic["last_poll_success"] and diagnostic["error_count"] == 0
                )
                assert diagnostic["poll_count"] >= 4
                messages, count = observer.snapshot()
                for topic, (_, retained, message_qos) in messages.items():
                    if topic.startswith(prefix + "/modsim01/data"):
                        assert retained is False and message_qos == qos
                if label == "td":
                    # Wait another complete cycle, allowing retained-message rejection to execute.
                    wait_for(
                        lambda: observer.snapshot()[1] > count + (65 if single else 1)
                    )
                    client = ModbusTcpClient("127.0.0.1", port=live_modsim)
                    try:
                        assert client.connect()
                        assert client.read_holding_registers(
                            40000, count=1, device_id=1
                        ).registers == [1]
                        commands = [
                            (
                                {"object_type": "coil", "address": 1, "value": True},
                                lambda d: d["coil01-08"][1] is True,
                            ),
                            (
                                {
                                    "object_type": "holding_register",
                                    "address": 40000,
                                    "value": 321,
                                },
                                lambda d: d["holding_reg01"] == 321,
                            ),
                            (
                                {
                                    "object_type": "holding_register",
                                    "address": 40001,
                                    "value": [11, 22, 33],
                                },
                                lambda d: [
                                    d["holding_reg02"],
                                    d["holding_reg03"],
                                    d["holding_reg04"],
                                ]
                                == [11, 22, 33],
                            ),
                        ]
                        for payload, condition in commands:
                            observer.publish(command_topic, json.dumps(payload))
                            wait_for(
                                lambda: condition(telemetry(observer, prefix, single))
                            )
                        assert (
                            client.read_coils(1, count=1, device_id=1).bits[0] is True
                        )
                        assert client.read_holding_registers(
                            40000, count=4, device_id=1
                        ).registers == [321, 11, 22, 33]
                    finally:
                        client.close()
            finally:
                process.terminate()
                try:
                    process.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
                stderr = process.stderr.read().decode()
                process.stderr.close()
                if sys.exc_info()[0] is None:
                    assert process.returncode == 0, stderr
    finally:
        if observer.client.is_connected():
            for topic in retained_topics:
                observer.publish(topic, b"", retain=True)
        observer.close()
