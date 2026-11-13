"""v1 CSV configuration loading and content-based format detection."""

from pathlib import Path

import pytest

from modpoll.config_loader import load_devices
from modpoll.csv_config import parse_csv

ROOT = Path(__file__).resolve().parents[1]
MODSIM_CSV = ROOT / "examples/modsim.csv"
MODSIM_TM = ROOT / "examples/modsim.tm.json"
MODSIM_TD = ROOT / "examples/modsim.generated.td.json"


def test_modsim_csv_loads_with_v1_row_semantics():
    (device,), model = load_devices(str(MODSIM_CSV), timeout=1)
    assert model is None
    assert device.name == "modsim01"
    assert device.devid == 1
    assert [(p.fc, p.start_address, p.size, p.endian) for p in device.pollerList] == [
        (1, 0, 16, "be_be"),
        (2, 10000, 16, "be_be"),
        (4, 30000, 20, "be_be"),
        (3, 40000, 44, "be_be"),
    ]
    assert len(device.points) == 37
    scaled = device.points["input_reg10"]
    assert scaled.address == 30010
    assert scaled.dtype == "uint32"
    assert float(scaled.scale) == 0.001
    assert device.points["holding_reg19"].dtype == "string16"
    assert device.points["coil01-08"].dtype == "bool8"


def test_csv_matches_tm_polling_structure():
    (csv_device,), _ = load_devices(str(MODSIM_CSV), timeout=1)
    (tm_device,), _ = load_devices(str(MODSIM_TM), timeout=1)
    csv_pollers = [
        (p.fc, p.start_address, p.size, p.endian) for p in csv_device.pollerList
    ]
    tm_pollers = [
        (p.fc, p.start_address, p.size, p.endian) for p in tm_device.pollerList
    ]
    assert csv_pollers == tm_pollers
    assert set(csv_device.points) == set(tm_device.points)
    for name, point in csv_device.points.items():
        tm_point = tm_device.points[name]
        if tm_point.dtype == "bool" and name.startswith(("coil", "di")):
            # Bit tables: v1 CSV names eight-bit groups, the TM names bits.
            base = 0 if name.startswith("coil") else 10000
            assert (point.address - base) * 8 == tm_point.address - base
            assert point.dtype == "bool8"
        else:
            assert (point.address, point.dtype) == (tm_point.address, tm_point.dtype)
        assert point.unit == tm_point.unit


def test_point_names_replace_spaces_and_blank_access_defaults_to_read():
    text = "device,meter,1\npoll,holding_register,0,4,BE_BE\nref,my point,0,uint16,\n"
    (device,) = parse_csv(text, source="<test>")
    assert "my_point" in device.points
    assert device.points["my_point"].rw == "r"
    assert device.points["my_point"] in device.pollerList[0].readablePoints


def test_csv_unit_id_override():
    (device,), _ = load_devices(str(MODSIM_CSV), timeout=1, unit_id=7)
    assert device.devid == 7


def test_duplicate_device_names_abort_the_load():
    text = "device,meter,1\ndevice,meter,2\n"
    with pytest.raises(ValueError, match="Duplicate device names"):
        parse_csv(text, source="<test>")


def test_invalid_rows_are_reported_and_skipped(caplog):
    text = "\n".join(
        [
            "device,meter,1",
            "poll,holding_register,0,2,BE_BE",
            "ref,good,0,uint16,r",
            "ref,bad-dtype,1,fancy16,r",
            "poll,coil,0,8,BE_BE",
            "ref,bit-on-coil,0:1,bool,r",
            "ref,out-of-range,99,uint16,r",
            "nonsense,row",
            "",
        ]
    )
    with caplog.at_level("WARNING"):
        (device,) = parse_csv(text, source="<test>")
    assert set(device.points) == {"good"}
    assert "unsupported data type" in caplog.text
    assert "Bit selectors require a register poller" in caplog.text
    assert "unknown row type" in caplog.text


def test_format_is_detected_from_content_not_filename(tmp_path):
    csv_named_json = tmp_path / "model.tm.json"
    csv_named_json.write_text("device,meter,1\n")
    devices, model = load_devices(str(csv_named_json), timeout=1)
    assert model is None and devices[0].name == "meter"

    json_named_csv = tmp_path / "legacy.csv"
    json_named_csv.write_text(MODSIM_TM.read_text())
    (_,), model = load_devices(str(json_named_csv), timeout=1)
    assert model is not None


def test_document_kind_assertion_at_loader_level():
    with pytest.raises(ValueError, match="document kind disagrees"):
        load_devices(str(MODSIM_TD), kind="tm", timeout=1)
    with pytest.raises(ValueError, match="document kind disagrees"):
        load_devices(str(MODSIM_TM), kind="td", timeout=1)
    with pytest.raises(ValueError, match="expected a Thing Model JSON document"):
        load_devices(str(MODSIM_CSV), kind="tm", timeout=1)
    (_,), model = load_devices(str(MODSIM_TM), kind="tm", timeout=1)
    assert model is not None


def test_csv_rejects_typed_parameters():
    with pytest.raises(ValueError, match="--param requires a Thing Model"):
        load_devices(str(MODSIM_CSV), timeout=1, parameters={"gain": 2})
