import sys

import pytest

from modpoll import main


def test_mqtt_tls_cli_options_forwarded(monkeypatch):
    captured = {}

    class FakeMqttHandler:
        def __init__(
            self,
            name,
            host,
            port,
            user,
            password,
            clientid,
            qos,
            subscribe_topics,
            use_tls,
            tls_version,
            cacerts,
            insecure,
            mqtt_version,
            log_level,
        ):
            captured["init"] = {
                "name": name,
                "host": host,
                "port": port,
                "user": user,
                "password": password,
                "clientid": clientid,
                "qos": qos,
                "subscribe_topics": subscribe_topics,
                "use_tls": use_tls,
                "tls_version": tls_version,
                "cacerts": cacerts,
                "insecure": insecure,
                "mqtt_version": mqtt_version,
                "log_level": log_level,
            }

        def setup(self):
            return True

        def connect(self):
            return True

        def close(self):
            captured["closed"] = True

        def receive(self):
            return None, None

    def fake_setup_modbus_handlers(args, mqtt_handler):
        captured["handler_instance"] = mqtt_handler
        # Stop execution before entering the main polling loop
        raise SystemExit(0)

    monkeypatch.setattr(main, "MqttHandler", FakeMqttHandler)
    monkeypatch.setattr(main, "setup_modbus_handlers", fake_setup_modbus_handlers)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "modpoll",
            "--config",
            "dummy.tm.json",
            "--tcp",
            "127.0.0.1",
            "--mqtt-host",
            "broker.local",
            "--mqtt-use-tls",
            "--mqtt-cacerts",
            "/tmp/ca.pem",
            "--mqtt-tls-version",
            "tlsv1.2",
            "--mqtt-version",
            "3.1.1",
            "--mqtt-insecure",
        ],
    )

    with pytest.raises(SystemExit) as excinfo:
        main.app()

    assert excinfo.value.code == 0
    init_args = captured["init"]
    assert init_args["use_tls"] is True
    assert init_args["tls_version"] == "tlsv1.2"
    assert init_args["cacerts"] == "/tmp/ca.pem"
    assert init_args["insecure"] is True
    assert init_args["mqtt_version"] == "3.1.1"
    assert init_args["subscribe_topics"] == ["modpoll/+/set"]


def test_mqtt_setup_close_errors_are_suppressed(monkeypatch):
    class FakeMqttHandler:
        def __init__(self, *args, **kwargs):
            pass

        def setup(self):
            raise RuntimeError("setup failed")

        def connect(self):
            return False

        def close(self):
            raise RuntimeError("close exploded")

    monkeypatch.setattr(main, "MqttHandler", FakeMqttHandler)
    monkeypatch.setattr(main, "setup_modbus_handlers", lambda args, mqtt_handler: [])
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "modpoll",
            "--config",
            "dummy.tm.json",
            "--tcp",
            "127.0.0.1",
            "--mqtt-host",
            "broker.local",
        ],
    )

    with pytest.raises(SystemExit) as excinfo:
        main.app()

    assert excinfo.value.code == 1


@pytest.mark.parametrize("utc_values", [(1000.0, 1.0, 2.0), (1.0, 1000000.0, 2.0)])
def test_poll_schedule_uses_monotonic_clock_when_utc_changes(monkeypatch, utc_values):
    polls = []
    clock = iter([10.0, 11.0, 16.0])
    utc = iter(utc_values)

    class Handler:
        def poll(self):
            polls.append(True)

        def close(self):
            pass

    monkeypatch.setattr(main, "setup_modbus_handlers", lambda args, mqtt: [Handler()])
    monkeypatch.setattr(main.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(main, "get_utc_time", lambda: next(utc))
    monkeypatch.setattr(main, "on_threading_event", lambda: len(polls) >= 2)
    monkeypatch.setattr(main, "delay_thread", lambda timeout: None)
    monkeypatch.setattr(
        sys,
        "argv",
        ["modpoll", "--config", "dummy.tm.json", "--tcp", "localhost", "--rate", "5"],
    )

    main.app()

    assert len(polls) == 2
