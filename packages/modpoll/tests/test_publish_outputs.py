"""MQTT telemetry shapes: grouped JSON, per-point topics and diagnostics."""

import json

from modpoll.modbus_task import Device, ModbusHandler, Point


class FakeClient:
    def connect(self):
        return True

    def close(self):
        pass


class FakeMqtt:
    def __init__(self):
        self.messages = []

    def publish(self, topic, payload, **kwargs):
        self.messages.append((topic, payload))


def make_handler():
    device = Device("meter", 1)
    scalar = Point(device, "voltage", "0", "uint16", "r", "V", None)
    scalar.update_value(230)
    flags = Point(device, "flags", "1", "bool8", "r", None, None)
    flags.update_value([True, False])
    stale = Point(device, "stale", "2", "uint16", "r", None, None)
    stale.update_value(None, valid=False)
    for point in (scalar, flags, stale):
        device.add_point_mapping(point)
    handler = ModbusHandler(FakeClient(), "unused.tm.json")
    handler.deviceList = [device]
    handler.mqtt_handler = FakeMqtt()
    handler.mqtt_publish_topic_pattern = "modbus/{{device_name}}/data"
    handler.mqtt_diagnostics_topic_pattern = "modbus/{{device_name}}/diagnostics"
    return handler, device


def test_grouped_publish_carries_valid_points_units_and_timestamp():
    handler, _ = make_handler()
    handler.publish_data(timestamp=1234.5)
    ((topic, payload),) = handler.mqtt_handler.messages
    assert topic == "modbus/meter/data"
    assert json.loads(payload) == {
        "voltage|V": 230,
        "flags": [True, False],
        "timestamp": 1234.5,
    }


def test_single_publish_uses_one_topic_per_point_and_per_list_entry():
    handler, _ = make_handler()
    handler.mqtt_single_publish = True
    handler.publish_data(timestamp=1234.5)
    assert handler.mqtt_handler.messages == [
        ("modbus/meter/data/voltage", 230),
        ("modbus/meter/data/flags/0", True),
        ("modbus/meter/data/flags/1", False),
    ]


def test_publish_is_a_no_op_without_a_pattern_or_handler():
    handler, _ = make_handler()
    handler.mqtt_publish_topic_pattern = None
    handler.publish_data()
    handler.mqtt_diagnostics_topic_pattern = None
    handler.publish_diagnostics()
    handler.mqtt_handler = None
    handler.publish_data()
    handler.publish_diagnostics()


def test_diagnostics_report_cycles_errors_and_last_result():
    handler, device = make_handler()
    device.pollCount, device.errorCount, device.pollSuccess = 7, 2, False
    handler.publish_diagnostics()
    ((topic, payload),) = handler.mqtt_handler.messages
    assert topic == "modbus/meter/diagnostics"
    assert json.loads(payload) == {
        "poll_count": 7,
        "error_count": 2,
        "last_poll_success": False,
    }
