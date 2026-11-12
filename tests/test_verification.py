"""Verification read and report (POLL-02a): per-group outcomes, report content and options."""

import json
import sys
import modpoll_wot
import pytest
from pymodbus.exceptions import ModbusIOException
from pymodbus.pdu import ExceptionResponse

from modpoll import main, modbus_task, utils, verification
from modpoll.arg_parser import get_parser

from .wot_helpers import meter_model, raw_form


@pytest.fixture(autouse=True)
def fresh_stop_event():
    """A finished run leaves the process-wide stop event set; each test starts a new run."""
    utils._thread_event.clear()
    yield
    utils._thread_event.clear()


def three_group_model():
    """Points `ok1` and `ok2` in one group, `refused` and `silent` each in their own."""
    model = meter_model("meter")
    model["properties"] = {
        name: {
            "type": "integer",
            "readOnly": True,
            "forms": [raw_form("uint16", address)],
        }
        for name, address in (("ok1", 0), ("ok2", 1), ("refused", 10), ("silent", 20))
    }
    model["modpoll:acquisition"] = [
        {
            "modv:entity": "HoldingRegister",
            "modv:address": 0,
            "modv:quantity": 2,
            "modpoll:members": ["ok1", "ok2"],
        },
        {
            "modv:entity": "HoldingRegister",
            "modv:address": 10,
            "modv:quantity": 1,
            "modpoll:members": ["refused"],
        },
        {
            "modv:entity": "HoldingRegister",
            "modv:address": 20,
            "modv:quantity": 1,
            "modpoll:members": ["silent"],
        },
    ]
    return model


class Answer:
    def __init__(self, registers):
        self.registers = registers

    def isError(self):
        return False


class FakeClient:
    """A device that answers address 0, refuses address 10 with exception 2 and ignores address 20."""

    def __init__(self, refuse=True, ignore=True):
        self.refuse, self.ignore, self.requests = refuse, ignore, []

    def connect(self):
        return True

    def close(self):
        pass

    def read_holding_registers(self, address, count, device_id):
        self.requests.append((address, count, device_id))
        if address == 10 and self.refuse:
            return ExceptionResponse(3, 2)
        if address == 20 and self.ignore:
            return ModbusIOException("no response")
        return Answer(list(range(100, 100 + count)))


def run_app(monkeypatch, argv, client):
    monkeypatch.setattr(modbus_task, "_create_modbus_client", lambda args: client)
    monkeypatch.setattr(sys, "argv", ["modpoll", "--interval", "0", *argv])
    monkeypatch.setattr(main, "logger", None)
    main.app()


def write_model(tmp_path, model):
    path = tmp_path / "meter.tm.json"
    path.write_text(json.dumps(model))
    return path


def test_full_read_records_each_group_and_never_retries(monkeypatch, tmp_path, capsys):
    path = write_model(tmp_path, three_group_model())
    report_path = tmp_path / "report.json"
    client = FakeClient()
    with pytest.raises(SystemExit) as exit_info:
        run_app(
            monkeypatch,
            [
                "-f",
                str(path),
                "--tcp",
                "192.0.2.10",
                "--unit-id",
                "7",
                "--report",
                str(report_path),
                "--confirm",
                "ok1",
                "--reject",
                "ok2",
            ],
            client,
        )
    assert exit_info.value.code == 1
    report = json.loads(report_path.read_text())
    assert [
        (p["property"], p["read"], p.get("exceptionCode"), p["expected"])
        for p in report["points"]
    ] == [
        ("ok1", "ok", None, "confirmed"),
        ("ok2", "ok", None, "rejected"),
        ("refused", "exception", 2, "unchecked"),
        ("silent", "no-response", None, "unchecked"),
    ]
    assert report["model"]["source"] == "local" and "ref" not in report["model"]
    assert "product" not in report and report["transport"] == "tcp"
    assert "environment" not in report
    assert report["tool"]["name"] == "modpoll"
    modpoll_wot.validate_report(report, model=path.read_bytes())
    # Nothing that identifies the device or what it answered is in the file.
    text = report_path.read_text()
    assert all(
        secret not in text for secret in ("192.0.2.10", '"unitId"', "100", "101")
    )
    assert [request[0] for request in client.requests] == [0, 10, 20]
    assert "Full read: 2 of 4 points read successfully." in capsys.readouterr().out


def test_full_read_of_a_healthy_device_succeeds_and_exports_a_snapshot(
    monkeypatch, tmp_path
):
    path = write_model(tmp_path, three_group_model())
    report_path, snapshot = tmp_path / "report.json", tmp_path / "snapshot.json"
    run_app(
        monkeypatch,
        [
            "-f",
            str(path),
            "--tcp",
            "192.0.2.10",
            "--report",
            str(report_path),
            "--export",
            str(snapshot),
            "--confirm",
            "all",
        ],
        FakeClient(refuse=False, ignore=False),
    )
    report = json.loads(report_path.read_text())
    assert {p["read"] for p in report["points"]} == {"ok"} and {
        p["expected"] for p in report["points"]
    } == {"confirmed"}
    assert json.loads(snapshot.read_text())["meter"]["ok1"] == 100


def test_report_goes_to_standard_output_with_dash(monkeypatch, tmp_path, capsys):
    path = write_model(tmp_path, three_group_model())
    run_app(
        monkeypatch,
        [
            "-f",
            str(path),
            "--tcp",
            "x",
            "--report",
            "-",
        ],
        FakeClient(False, False),
    )
    out = capsys.readouterr().out
    assert json.loads(out[out.index("{") : out.rindex("}") + 1])["reportVersion"] == 4


def test_a_point_that_was_not_read_cannot_be_judged(monkeypatch, tmp_path):
    path = write_model(tmp_path, three_group_model())
    with pytest.raises(SystemExit) as exit_info:
        run_app(
            monkeypatch,
            [
                "-f",
                str(path),
                "--tcp",
                "x",
                "--report",
                str(tmp_path / "r.json"),
                "--confirm",
                "refused",
            ],
            FakeClient(),
        )
    assert exit_info.value.code == 1
    assert not (tmp_path / "r.json").exists()


@pytest.mark.parametrize(
    "argv, message",
    [
        ([], "One of --config/-f is required"),
        (
            ["-f", "x.json", "--confirm", "all", "--tcp", "x"],
            "need --report or --upload",
        ),
        (["-f", "x.json", "--tcp", "x", "--yes"], "--yes needs --upload"),
        (
            ["-f", "x.json", "--report", "r.json", "--tcp", "x", "--timeout", "30"],
            "at most 10",
        ),
        (["-f", "x.json", "--report", "r.json", "--udp", "x"], "not UDP"),
        (
            ["-f", "x.json", "--report", "r.json", "--rtu", "p", "--framer", "ascii"],
            "not Modbus ASCII",
        ),
        (
            ["-f", "x.json", "--report", "r.json", "--tcp", "x", "--mqtt-host", "h"],
            "not published to MQTT",
        ),
        (
            ["-f", "a.json", "b.json", "--report", "r.json", "--tcp", "x"],
            "reads one Thing Model",
        ),
    ],
)
def test_option_combinations_are_refused(argv, message, monkeypatch, caplog):
    monkeypatch.setattr(sys, "argv", ["modpoll", *argv])
    monkeypatch.setattr(main, "logger", None)
    with pytest.raises(SystemExit) as exit_info:
        main.app()
    assert exit_info.value.code == 2
    assert message in caplog.text


def test_a_report_read_asks_each_group_once():
    args = get_parser().parse_args(["-f", "x", "--tcp", "h"])
    args.full_read = True
    assert modbus_task._read_options(args) == {"retries": 0}
    args.full_read = False
    assert modbus_task._read_options(args) == {}


def test_bare_report_interactively_saves_and_judges(monkeypatch, tmp_path, capsys):
    """--report without FILE asks where to save and whether the values look right."""
    path = write_model(tmp_path, three_group_model())
    monkeypatch.chdir(tmp_path)
    answers = iter(["y", ""])  # values look right; save to the default name
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))
    run_app(
        monkeypatch,
        ["-f", str(path), "--tcp", "192.0.2.10", "--report"],
        FakeClient(False, False),
    )
    (saved,) = tmp_path.glob("report-*.json")
    report = json.loads(saved.read_text())
    assert {p["expected"] for p in report["points"]} == {"confirmed"}
    assert "product" not in report


def test_bare_report_without_a_terminal_names_a_file(monkeypatch, tmp_path, caplog):
    path = write_model(tmp_path, three_group_model())
    with pytest.raises(SystemExit) as exit_info:
        run_app(
            monkeypatch,
            ["-f", str(path), "--tcp", "x", "--report"],
            FakeClient(False, False),
        )
    assert exit_info.value.code == 1
    assert "Add --report FILE" in caplog.text
