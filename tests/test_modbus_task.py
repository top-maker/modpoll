import os

from tests.wot_helpers import write_meter
import pytest  # type: ignore
from modpoll.arg_parser import get_parser
from modpoll.modbus_task import setup_modbus_handlers


@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("MODPOLL_PUBLIC_NETWORK"),
    reason="reads the public modsim.topmaker.net; set MODPOLL_PUBLIC_NETWORK=1 to run",
)
def test_modbus_task_poll_modsim():
    parser = get_parser()
    args = parser.parse_args(
        [
            "--config",
            "examples/modsim.tm.json",
            "--tcp",
            "modsim.topmaker.net",
        ]
    )
    modbus_handlers = setup_modbus_handlers(args)
    modbus_handler = modbus_handlers[0]

    assert modbus_handler.connect()

    modbus_handler.poll()

    # Check if any data was collected
    assert len(modbus_handler.deviceList) > 0
    assert len(modbus_handler.deviceList[0].points) > 0

    # Check if at least one reference has a non-None value
    assert any(
        point.val is not None for point in modbus_handler.deviceList[0].points.values()
    )

    modbus_handler.disconnect()
    modbus_handler.close()


def test_each_configuration_owns_its_client(monkeypatch, tmp_path):
    from modpoll import modbus_task

    clients = []

    class Client:
        def __init__(self):
            self.closed = 0
            clients.append(self)

        def connect(self):
            return True

        def close(self):
            self.closed += 1

    monkeypatch.setattr(modbus_task, "_create_modbus_client", lambda args: Client())
    valid = write_meter(tmp_path / "valid.tm.json")
    second = write_meter(tmp_path / "second.tm.json", name="second")
    missing = tmp_path / "missing.tm.json"
    args = get_parser().parse_args(
        ["--config", str(valid), str(missing), str(second), "--tcp", "localhost"]
    )
    handlers = setup_modbus_handlers(args)

    assert len(handlers) == 2
    assert handlers[0].modbus_client is clients[0]
    assert len(clients) == 2  # Invalid files do not allocate a transport client.
    assert handlers[1].modbus_client is clients[1]
    assert handlers[0].connect()
    handlers[0].close()
    assert clients[0].closed == 1
    assert clients[1].closed == 0
    assert handlers[1].connect()
    handlers[1].close()
    assert clients[1].closed == 1


def test_setup_closes_previously_created_handlers_on_initialization_failure(
    monkeypatch,
):
    from modpoll import modbus_task

    handlers = []

    class StubHandler:
        def __init__(self, client, config, *args, **kwargs):
            self.config = config
            self.model = None
            self.closed = False
            handlers.append(self)

        def load_config(self):
            if self.config == "broken.tm.json":
                raise RuntimeError("cannot load configuration")
            return True

        def get_device_list(self):
            return []

        def close(self):
            self.closed = True

    monkeypatch.setattr(modbus_task, "_create_modbus_client", lambda args: object())
    monkeypatch.setattr(modbus_task, "ModbusHandler", StubHandler)
    args = get_parser().parse_args(
        ["--config", "valid.tm.json", "broken.tm.json", "--tcp", "localhost"]
    )
    with pytest.raises(RuntimeError, match="cannot load"):
        setup_modbus_handlers(args)
    assert [handler.closed for handler in handlers] == [True, True]


def test_duplicate_device_names_across_configs_fail_before_polling(
    monkeypatch, tmp_path
):
    from modpoll import modbus_task

    monkeypatch.setattr(modbus_task, "_create_modbus_client", lambda args: object())
    first = write_meter(tmp_path / "first.tm.json")
    second = write_meter(tmp_path / "second.tm.json")
    args = get_parser().parse_args(
        ["--config", str(first), str(second), "--tcp", "localhost"]
    )
    with pytest.raises(ValueError, match="Duplicate device names.*meter"):
        setup_modbus_handlers(args)
