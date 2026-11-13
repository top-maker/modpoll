import signal
import sys

import pytest

from modpoll import main


def test_sigterm_is_registered_and_resources_close_after_poll_error(monkeypatch):
    closed = []
    registered = []

    class FakeMqttHandler:
        def __init__(self, *args, **kwargs):
            pass

        def setup(self):
            return True

        def connect(self):
            return True

        def close(self):
            closed.append("mqtt")

    class FakeModbusHandler:
        def poll(self):
            raise RuntimeError("poll failed")

        def close(self):
            closed.append("modbus")

    monkeypatch.setattr(main, "MqttHandler", FakeMqttHandler)
    monkeypatch.setattr(
        main, "setup_modbus_handlers", lambda args, mqtt_handler: [FakeModbusHandler()]
    )
    monkeypatch.setattr(main, "delay_thread", lambda timeout=0: None)
    monkeypatch.setattr(main, "on_threading_event", lambda: False)
    monkeypatch.setattr(main, "set_threading_event", lambda: None)
    monkeypatch.setattr(
        main,
        "signal",
        type(
            "Signals",
            (),
            {
                "signal": lambda sig, fn: registered.append(sig),
                "SIGINT": signal.SIGINT,
                "SIGTERM": signal.SIGTERM,
            },
        ),
    )
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

    with pytest.raises(RuntimeError, match="poll failed"):
        main.app()

    assert signal.SIGTERM in registered
    assert closed == ["modbus", "mqtt"]


def test_signal_handler_tolerates_uninitialized_logger(monkeypatch):
    called = []
    monkeypatch.setattr(main, "logger", None)
    monkeypatch.setattr(main, "set_threading_event", lambda: called.append(True))

    main._signal_handler(signal.SIGTERM, None)

    assert called == [True]
