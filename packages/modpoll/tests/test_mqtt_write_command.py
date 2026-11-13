import json

from modpoll.main import process_mqtt_command


class FakeHandler:
    def __init__(self, devices):
        self.devices = devices
        self.writes = []

    def get_device_list(self):
        return self.devices

    def write_coil(self, *args):
        self.writes.append(("coil", args))
        return True

    def write_register(self, *args):
        self.writes.append(("holding_register", args))
        return True


def test_valid_register_command_routes_one_topic_level():
    handler = FakeHandler([type("Device", (), {"name": "meter.+"})()])

    assert process_mqtt_command(
        "modpoll/meter.+/set",
        json.dumps({"object_type": "holding_register", "address": 10, "value": 7}),
        False,
        "modpoll/+/set",
        [handler],
    )
    assert handler.writes == [("holding_register", ("meter.+", 10, 7))]


def test_malformed_retained_and_ambiguous_commands_do_not_write():
    device = type("Device", (), {"name": "meter"})()
    one = FakeHandler([device])
    two = FakeHandler([device])
    pattern = "modpoll/+/set"
    valid = json.dumps({"object_type": "coil", "address": 1, "value": True})

    for payload, retained, handlers in [
        (b"[1,2]", False, [one]),
        (b"\xff", False, [one]),
        (valid, True, [one]),
        (valid, False, [one, two]),
        (valid, False, [FakeHandler([device, device])]),
    ]:
        assert not process_mqtt_command(
            "modpoll/meter/set", payload, retained, pattern, handlers
        )
    assert one.writes == []
    assert two.writes == []


def test_invalid_write_fields_do_not_reach_handler():
    handler = FakeHandler([type("Device", (), {"name": "meter"})()])
    for value in [-1, 65536, True, 7.0, "7"]:
        payload = json.dumps(
            {"object_type": "holding_register", "address": 10, "value": value}
        )
        assert not process_mqtt_command(
            "modpoll/meter/set", payload, False, "modpoll/+/set", [handler]
        )
    assert not process_mqtt_command(
        "modpoll/meter/set",
        json.dumps({"object_type": "holding_register", "address": 65536, "value": 7}),
        False,
        "modpoll/+/set",
        [handler],
    )
    assert handler.writes == []


def test_documented_multiple_register_mqtt_command_is_accepted():
    handler = FakeHandler([type("Device", (), {"name": "meter"})()])
    payload = json.dumps(
        {"object_type": "holding_register", "address": 10, "value": [1, 2]}
    )

    assert process_mqtt_command(
        "modpoll/meter/set", payload, False, "modpoll/+/set", [handler]
    )
    assert handler.writes == [("holding_register", ("meter", 10, [1, 2]))]
