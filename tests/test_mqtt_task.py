import os
import pytest
import time
import queue
from modpoll.mqtt_task import MqttHandler


def test_mqtt_task_setup():
    mqtt_handler = MqttHandler(
        name="test_mqtt",
        host="broker.emqx.io",
        port=1883,
        user=None,
        password=None,
        clientid="test_client_13579",
        qos=0,
        subscribe_topics=["test/topic"],
    )

    assert mqtt_handler.setup()

    # Test MQTT client properties
    assert mqtt_handler.mqtt_client is not None
    assert mqtt_handler.host == "broker.emqx.io"
    assert mqtt_handler.port == 1883

    # Clean up
    mqtt_handler.close()


def test_receive_empty_queue_returns_none():
    handler = MqttHandler(
        name="test_mqtt",
        host="broker.emqx.io",
        port=1883,
        user=None,
        password=None,
        clientid="test_client_13579",
        qos=0,
    )

    topic, payload, retained = handler.receive()

    assert topic is None
    assert payload is None
    assert retained is False


def test_receive_returns_message_when_available():
    handler = MqttHandler(
        name="test_mqtt",
        host="broker.emqx.io",
        port=1883,
        user=None,
        password=None,
        clientid="test_client_13579",
        qos=0,
    )

    class FakeQueue:
        def get(self, block=False):
            return ("some/topic", b"payload", True)

    handler.rx_queue = FakeQueue()

    topic, payload, retained = handler.receive()

    assert topic == "some/topic"
    assert payload == b"payload"
    assert retained is True


def test_message_callback_preserves_retained_flag():
    handler = MqttHandler(
        name="test_mqtt",
        host="broker.local",
        port=1883,
        user=None,
        password=None,
        clientid="test_client",
        qos=0,
    )

    class Message:
        topic = "modpoll/meter/set"
        payload = b"{}"
        retain = 1

    handler.rx_queue = queue.Queue(maxsize=1000)
    handler._on_message(None, None, Message())
    assert handler.receive() == ("modpoll/meter/set", b"{}", True)


def test_message_is_immediately_available_on_default_queue():
    handler = MqttHandler("test", "localhost", 1883, None, None, None, 0)
    message = type("Message", (), {"topic": "a", "payload": b"x", "retain": 0})()
    handler._on_message(None, None, message)
    assert handler.receive() == ("a", b"x", False)


def test_publish_when_connected_calls_client_publish():
    handler = MqttHandler(
        name="test_mqtt",
        host="broker.emqx.io",
        port=1883,
        user=None,
        password=None,
        clientid="test_client_13579",
        qos=1,
    )

    class StubClient:
        def __init__(self):
            self.calls = []

        def is_connected(self):
            return True

        def publish(self, topic, msg, qos, retain):
            self.calls.append((topic, msg, qos, retain))

            class PubInfo:
                rc = 0

            return PubInfo()

    stub = StubClient()
    handler.mqtt_client = stub

    result = handler.publish("topic", "message", qos=2, retain=True)

    assert result.rc == 0
    assert stub.calls == [("topic", "message", 2, True)]


def test_setup_respects_tls_option(monkeypatch):
    called = {}
    handler = MqttHandler(
        name="test_mqtt",
        host="broker.emqx.io",
        port=8883,
        user=None,
        password=None,
        clientid="client",
        qos=0,
        subscribe_topics=["secure/topic"],
        use_tls=True,
        tls_version="tlsv1.2",
        mqtt_version="3.1.1",
    )

    def fake_setup_tls():
        called["tls"] = True

    monkeypatch.setattr(handler, "_setup_tls", fake_setup_tls)

    assert handler.setup()
    assert called.get("tls") is True
    assert handler.mqtt_client is not None


def test_publish_skips_when_disconnected_qos0(monkeypatch):
    handler = MqttHandler(
        name="test_mqtt",
        host="broker.emqx.io",
        port=1883,
        user=None,
        password=None,
        clientid="test_client_13579",
        qos=0,
    )

    class StubClient:
        def is_connected(self):
            return False

    handler.mqtt_client = StubClient()

    result = handler.publish("topic", "msg")

    assert result is None


def test_connect_mqtt_v311_omits_clean_session_kwarg(monkeypatch):
    """paho-mqtt 2.x rejects clean_session in connect(); it is set on the Client constructor."""
    handler = MqttHandler(
        name="test_mqtt",
        host="broker.local",
        port=1883,
        user=None,
        password=None,
        clientid="test_client",
        qos=0,
        mqtt_version="3.1.1",
    )

    assert handler.setup()

    captured = {}

    def fake_connect(**kwargs):
        captured.update(kwargs)
        return 0

    monkeypatch.setattr(handler.mqtt_client, "connect", fake_connect)

    class Flags:
        session_present = False

    def fake_loop_start():
        handler._on_connect(handler.mqtt_client, None, Flags(), 0, None)

    monkeypatch.setattr(handler.mqtt_client, "loop_start", fake_loop_start)

    assert handler.connect() is True
    assert "clean_session" not in captured
    assert captured == {
        "host": "broker.local",
        "port": 1883,
        "keepalive": 60,
    }


def test_publish_attempts_reconnect_when_disconnected_qos1(monkeypatch):
    handler = MqttHandler(
        name="test_mqtt",
        host="broker.emqx.io",
        port=1883,
        user=None,
        password=None,
        clientid="test_client_13579",
        qos=1,
    )

    class StubClient:
        def is_connected(self):
            return False

    handler.mqtt_client = StubClient()

    called = {}

    def fake_connect():
        called["connect"] = True
        return False

    monkeypatch.setattr(handler, "connect", fake_connect)

    result = handler.publish("topic", "msg")

    assert result is None
    assert called.get("connect") is True


@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("MODPOLL_PUBLIC_NETWORK")
    and not os.environ.get("MODPOLL_MQTT_HOST"),
    reason="connects to a public broker; set MODPOLL_PUBLIC_NETWORK=1 or MODPOLL_MQTT_HOST",
)
def test_mqtt_task_connect():
    import os
    import uuid

    mqtt_handler = MqttHandler(
        name="test_mqtt",
        host=os.environ.get("MODPOLL_MQTT_HOST", "broker.emqx.io"),
        port=int(os.environ.get("MODPOLL_MQTT_PORT", "1883")),
        user=None,
        password=None,
        clientid="modpoll-test-" + uuid.uuid4().hex,
        qos=0,
    )

    assert mqtt_handler.setup()
    assert mqtt_handler.connect()

    # Add a short delay to allow the connection to establish
    time.sleep(1)

    # Test connection
    assert mqtt_handler.is_connected()

    # Clean up
    mqtt_handler.close()


def test_connect_waits_for_connack_and_reports_rejection(monkeypatch):
    handler = MqttHandler(
        name="test_mqtt",
        host="broker.local",
        port=1883,
        user=None,
        password=None,
        clientid="test_client",
        qos=0,
    )
    assert handler.setup()

    class StubClient:
        def connect(self, **kwargs):
            return 0

        def loop_start(self):
            handler._on_connect(
                self, None, type("Flags", (), {"session_present": False})(), 5, None
            )

        def loop_stop(self):
            pass

        def is_connected(self):
            return False

    handler.mqtt_client = StubClient()
    assert handler.connect() is False
    assert not handler.is_connected()


def test_connect_reports_success_after_connack():
    handler = MqttHandler(
        name="test_mqtt",
        host="broker.local",
        port=1883,
        user=None,
        password=None,
        clientid="test_client",
        qos=0,
    )
    assert handler.setup()

    class StubClient:
        def connect(self, **kwargs):
            return 0

        def loop_start(self):
            handler._on_connect(
                self, None, type("Flags", (), {"session_present": False})(), 0, None
            )

        def is_connected(self):
            return True

    handler.mqtt_client = StubClient()
    assert handler.connect() is True
    assert handler.is_connected()


def test_received_payload_is_logged_at_debug_not_info(caplog):
    import logging

    handler = MqttHandler("t", "broker.local", 1883, None, None, "c", 0)
    message = type(
        "M", (), {"retain": 0, "topic": "a/b", "payload": b"\x00\xffsecret"}
    )()
    with caplog.at_level(logging.DEBUG):
        handler._on_message(None, None, message)
    info = [r.getMessage() for r in caplog.records if r.levelno == logging.INFO]
    debug = [r.getMessage() for r in caplog.records if r.levelno == logging.DEBUG]
    assert any("a/b" in line for line in info)
    assert not any("secret" in line for line in info)
    assert any("secret" in line for line in debug)
