"""One rendering rule for the console, the MQTT payload and the JSON export."""

from decimal import Decimal
import json
import logging
import struct

import pytest

from modpoll.arg_parser import get_parser
from modpoll.modbus_task import Device, ModbusHandler, Point
from modpoll.precision import names_same_raw, parse_precision, render_value


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


def scaled_point(device, name, raw, multiplier):
    """A point whose register value is scaled by a multiplier."""
    point = Point(device, name, "0", "uint32", "r", None, Decimal(multiplier))
    point.update_value(raw)
    return point


def make_handler(points, precision=None):
    device = Device("meter", 1)
    for point in points:
        device.add_point_mapping(point)
    handler = ModbusHandler(FakeClient(), "unused.tm.json", precision=precision)
    handler.deviceList = [device]
    return handler


def table_values(text):
    """The value column of every terminal table row."""
    values = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("|"):
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if cells[0] not in ("Point", "Reference"):
                values.append(cells[1])
    return values


def warning_records(caplog):
    """The warnings the run logged."""
    return [record for record in caplog.records if record.levelno == logging.WARNING]


def test_parse_precision_reads_auto_and_counts():
    assert parse_precision("auto") is None
    assert parse_precision("AUTO") is None
    assert parse_precision(None) is None
    assert parse_precision("3") == 3
    assert parse_precision(0) == 0


@pytest.mark.parametrize("text", ["-1", "abc", "1.5"])
def test_parse_precision_rejects_values_that_are_not_a_count(text):
    with pytest.raises(ValueError):
        parse_precision(text)


def test_auto_scaled_reading_keeps_the_exact_decimal():
    point = scaled_point(Device("meter", 1), "temperature", 2301, "0.1")
    rendered = render_value(
        point.val, None, raw=point.raw_val, multiplier=point.exact_multiplier
    )

    assert point.val == 230.10000000000002
    assert rendered == 230.1


def test_auto_scaled_reading_does_not_collapse_a_fine_multiplier():
    point = scaled_point(Device("meter", 1), "fine", 1, "0.0001")
    rendered = render_value(
        point.val, None, raw=point.raw_val, multiplier=point.exact_multiplier
    )

    assert rendered == 0.0001


def test_auto_float32_uses_the_shortest_decimal_of_that_width():
    value = struct.unpack(">f", struct.pack(">f", 12.34))[0]

    assert value != 12.34
    assert render_value(value, None, dtype="float32") == 12.34


def test_auto_float64_keeps_the_value_it_read():
    assert render_value(0.123456789, None, dtype="float64") == 0.123456789


def test_auto_leaves_integers_untouched():
    assert render_value(42, None, dtype="uint16") == 42
    assert render_value(True, None, dtype="bool") is True


def test_explicit_precision_rounds_every_float():
    value = struct.unpack(">f", struct.pack(">f", 12.34))[0]

    assert render_value(value, 2, dtype="float32") == 12.34
    assert render_value(0.123456789, 3, dtype="float64") == 0.123
    assert render_value(0.123456789, 0, dtype="float64") == 0.0


def test_explicit_precision_truncates_a_scaled_reading_as_asked():
    point = scaled_point(Device("meter", 1), "fine", 1, "0.0001")
    rendered = render_value(
        point.val, 3, raw=point.raw_val, multiplier=point.exact_multiplier
    )

    assert rendered == 0.0
    assert not names_same_raw(0.0, 1, Decimal("0.0001"))


def test_console_mqtt_and_export_show_the_same_number(capsys, tmp_path):
    device = Device("meter", 1)
    point = scaled_point(device, "temperature", 2301, "0.1")
    device.add_point_mapping(point)
    handler = make_handler([point])
    mqtt = FakeMqtt()
    handler.mqtt_handler = mqtt
    handler.mqtt_publish_topic_pattern = "test/{{device_name}}/data"

    handler.print_results()
    handler.publish_data()
    handler.export(tmp_path / "snapshot.json")

    table = capsys.readouterr().out
    payload = json.loads(mqtt.messages[-1][1])
    snapshot = json.loads((tmp_path / "snapshot.json").read_text())
    assert table_values(table) == ["230.1"]
    assert payload["temperature"] == 230.1
    assert snapshot["meter"]["temperature"] == 230.1


def test_explicit_precision_reaches_every_output(capsys, tmp_path):
    device = Device("meter", 1)
    point = scaled_point(device, "temperature", 12345678, "0.001")
    device.add_point_mapping(point)
    handler = make_handler([point], precision=2)
    mqtt = FakeMqtt()
    handler.mqtt_handler = mqtt
    handler.mqtt_publish_topic_pattern = "test/{{device_name}}/data"

    handler.print_results()
    handler.publish_data()
    handler.export(tmp_path / "snapshot.json")

    table = capsys.readouterr().out
    payload = json.loads(mqtt.messages[-1][1])
    snapshot = json.loads((tmp_path / "snapshot.json").read_text())
    assert table_values(table) == ["12345.68"]
    assert payload["temperature"] == 12345.68
    assert snapshot["meter"]["temperature"] == 12345.68


def test_export_warns_once_when_truncation_changes_the_raw_value(caplog, tmp_path):
    device = Device("meter", 1)
    point = scaled_point(device, "fine", 1, "0.0001")
    device.add_point_mapping(point)
    handler = make_handler([point], precision=3)

    with caplog.at_level(logging.WARNING):
        handler.export(tmp_path / "snapshot.json")
        handler.export(tmp_path / "snapshot.json")

    warnings = warning_records(caplog)
    assert len(warnings) == 1
    assert "fine" in warnings[0].getMessage()
    assert json.loads((tmp_path / "snapshot.json").read_text())["meter"]["fine"] == 0.0


def test_export_does_not_warn_when_the_raw_value_survives(caplog, tmp_path):
    device = Device("meter", 1)
    point = scaled_point(device, "temperature", 2301, "0.1")
    device.add_point_mapping(point)
    handler = make_handler([point], precision=1)

    with caplog.at_level(logging.WARNING):
        handler.export(tmp_path / "snapshot.json")

    assert not warning_records(caplog)


def test_cli_accepts_auto_and_a_count():
    parser = get_parser()

    assert parser.parse_args(["-f", "c.tm.json"]).precision is None
    auto = parser.parse_args(["-f", "c.tm.json", "--precision", "auto"])
    assert auto.precision is None
    assert parser.parse_args(["-f", "c.tm.json", "--precision", "4"]).precision == 4


@pytest.mark.parametrize("text", ["-1", "abc"])
def test_cli_rejects_a_precision_that_is_not_a_count(text):
    parser = get_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["-f", "c.tm.json", "--precision", text])


@pytest.mark.parametrize("text", [True, "abc", "1.5", -1, "-2"])
def test_invalid_precision_is_rejected(text):
    with pytest.raises(ValueError):
        parse_precision(text)


def test_precision_accepts_auto_count_and_blank():
    assert parse_precision(None) is None
    assert parse_precision(" AUTO ") is None
    assert parse_precision("") is None
    assert parse_precision("3") == 3
    assert parse_precision(0) == 0


@pytest.mark.parametrize("multiplier", [Decimal("sNaN"), Decimal(0), Decimal("1E+500")])
def test_unusable_multipliers_fall_back_to_the_value_without_raising(multiplier):
    # No branch may turn a reading into a wrong number or an exception.
    for precision in (None, 3):
        rendered = render_value(1.5, precision, raw=3, multiplier=multiplier)
        assert rendered == 1.5 or precision == 3


def test_exact_decimal_too_wide_to_quantize_keeps_its_value():
    assert render_value(1e40, 2, raw=1, multiplier=Decimal("1E+40")) == 1e40


def test_exact_decimal_beyond_float_range_falls_back_to_the_reading():
    assert render_value(1.5, None, raw=1, multiplier=Decimal("1E+400")) == 1.5


@pytest.mark.parametrize(
    "value, dtype, expected",
    [
        (12.34000015258789, "float32", 12.34),
        (0.1, "float32", 0.1),
        (1e300, "float32", 1e300),
        (float("inf"), "float32", float("inf")),
        (1.5, "uint16", 1.5),
    ],
)
def test_register_width_shortest_decimal(value, dtype, expected):
    assert render_value(value, None, dtype=dtype) == expected


@pytest.mark.parametrize("multiplier", [Decimal(0), Decimal("sNaN")])
def test_a_value_that_cannot_be_inverted_does_not_name_the_raw(multiplier):
    assert not names_same_raw(1.5, 3, multiplier)
