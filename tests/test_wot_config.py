"""Application adapter regression tests independent of a live device."""

import json
from pathlib import Path

import pytest

from modpoll.modbus_task import ModbusHandler
from modpoll.wot_config import read_model, create_devices
from tests.wot_helpers import meter_model, write_meter


def test_csv_content_is_rejected_without_partial_device(tmp_path, caplog):
    path = tmp_path / "old.csv"
    path.write_text(
        "device,meter,1\npoll,holding_register,0,1,BE_BE\nref,x,0,uint16,r\n"
    )
    handler = ModbusHandler(object(), str(path))
    assert not handler.load_config()
    assert handler.deviceList == []
    assert "Invalid WoT configuration" in caplog.text


def test_url_model_loader_keeps_timeout_and_streams(monkeypatch):
    from modpoll import wot_config

    payload = json.dumps(meter_model()).encode()
    calls = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def raise_for_status(self):
            pass

        def iter_content(self, size):
            yield payload[:20]
            yield payload[20:]

    def get(url, **kwargs):
        calls.append((url, kwargs))
        return Response()

    monkeypatch.setattr(wot_config.requests, "get", get)
    model = read_model("https://example.test/model.tm.json", timeout=2.5, unit_id=7)
    assert model.unit_id == 7
    assert calls == [
        ("https://example.test/model.tm.json", {"timeout": 2.5, "stream": True})
    ]


def test_adapter_preserves_all_modsim_point_addresses():
    path = Path(__file__).resolve().parents[1] / "examples/modsim.tm.json"
    (device,) = create_devices(read_model(str(path), timeout=1, unit_id=7))
    assert device.name == "modsim01" and device.devid == 7
    assert [(p.fc, p.start_address, p.size) for p in device.pollerList] == [
        (1, 0, 16),
        (2, 10000, 16),
        (4, 30000, 20),
        (3, 40000, 44),
    ]
    assert len(device.points) == 37
    assert device.points["coil09-16"].address == 8
    assert device.points["di09-16"].address == 10008
    assert device.points["holding_reg19"].dtype == "string16"
    assert device.points["holding_reg10"].scale == 0.001
    assert device.points["input_reg01"].rw == "r"
    assert device.points["holding_reg01"].rw == "rw"


def test_unit_id_validation_fails_before_connect(tmp_path):
    config = write_meter(tmp_path / "meter.tm.json")
    handler = ModbusHandler(object(), str(config), unit_id=0)
    assert not handler.load_config()


@pytest.mark.parametrize("kind", ["tm", "td"])
@pytest.mark.parametrize("filename", ["device", "device.tm.json", "device.td.json"])
def test_single_config_option_loads_content_regardless_of_filename(
    tmp_path, kind, filename
):
    from modpoll.arg_parser import get_parser

    source_name = {
        "tm": "modsim.tm.json",
        "td": "modsim.generated.td.json",
    }[kind]
    source = Path(__file__).resolve().parents[1] / "examples" / source_name
    path = tmp_path / filename
    path.write_bytes(source.read_bytes())
    args = get_parser().parse_args(["--config", str(path)])
    model = read_model(args.config[0], timeout=1, unit_id=None)
    assert model.kind == kind
    handler = ModbusHandler(object(), args.config[0])
    assert handler.load_config()
    (device,) = handler.deviceList
    assert len(device.points) == 37
    assert [(p.fc, p.start_address, p.size) for p in device.pollerList] == [
        (1, 0, 16),
        (2, 10000, 16),
        (4, 30000, 20),
        (3, 40000, 44),
    ]


@pytest.mark.parametrize("kind", ["tm", "td"])
def test_remote_config_detects_response_content_at_opaque_url(monkeypatch, kind):
    from modpoll import wot_config

    source_name = {
        "tm": "modsim.tm.json",
        "td": "modsim.generated.td.json",
    }[kind]
    source = Path(__file__).resolve().parents[1] / "examples" / source_name

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def raise_for_status(self):
            pass

        def iter_content(self, size):
            yield source.read_bytes()

    monkeypatch.setattr(wot_config.requests, "get", lambda *a, **kw: Response())
    model = read_model("https://example.test/config/42", timeout=1, unit_id=None)
    assert model.kind == kind
    assert len(model.groups) == 4


@pytest.mark.parametrize("remote", [False, True], ids=["local", "https"])
@pytest.mark.parametrize("kind", ["tm", "td"])
def test_profile_01_is_rejected_before_device_execution(
    tmp_path, monkeypatch, remote, kind
):
    from modpoll import wot_config

    # A valid old-format model also exercises the guard with the registry wheel,
    # which still understands 0.1 until the cleaned producer is published.
    document = {
        "@context": [
            "https://www.w3.org/2022/wot/td/v1.1",
            {
                "modpoll": "https://top-maker.github.io/modpoll/vocab/wot-modbus#",
                "modv": "https://www.w3.org/2019/wot/modbus",
            },
        ],
        "title": "old-device",
        "modpoll:version": "0.1",
        "properties": {"value": {"type": "integer", "readOnly": True}},
        "modpoll:acquisition": [
            {
                "modv:entity": "HoldingRegister",
                "modv:address": 0,
                "modv:quantity": 1,
                "modv:mostSignificantByte": True,
                "modv:mostSignificantWord": True,
                "modpoll:members": [
                    {
                        "modpoll:property": "value",
                        "modpoll:offset": 0,
                        "modpoll:dataType": "uint16",
                    }
                ],
            }
        ],
    }
    if kind == "tm":
        document["@type"] = "tm:ThingModel"
    else:
        document["securityDefinitions"] = {"none": {"scheme": "nosec"}}
        document["security"] = "none"
        document["properties"]["value"]["forms"] = [
            {
                "href": "modbus+tcp://localhost:5020/1/0?quantity=1",
                "modv:entity": "HoldingRegister",
                "op": "readproperty",
            }
        ]
    payload = json.dumps(document).encode()
    if remote:

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def raise_for_status(self):
                pass

            def iter_content(self, size):
                yield payload

        monkeypatch.setattr(wot_config.requests, "get", lambda *a, **kw: Response())
        location = "https://example.test/old-device"
    else:
        path = tmp_path / "old-device.json"
        path.write_bytes(payload)
        location = str(path)
    with pytest.raises(ValueError, match="expected.*0.2"):
        read_model(location, timeout=1, unit_id=None)
    handler = ModbusHandler(object(), location)
    assert not handler.load_config()
    assert handler.deviceList == []
