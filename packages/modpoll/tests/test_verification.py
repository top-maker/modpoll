"""Verification read and report (POLL-02a): per-group outcomes, report content and options."""

import hashlib
import json
import os
import re
import sys
import urllib.parse
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


def saved_report(model, *, transport="tcp"):
    """A schema-5 report for a model, as a read on a device would have written it."""
    return {
        "reportVersion": 5,
        "model": {
            "sha256": hashlib.sha256(model).hexdigest(),
            "fingerprint": modpoll_wot.model_fingerprint(model),
            "source": "local",
        },
        "tool": {"name": "modpoll", "version": "2.0.0a8", "interpreter": "0.6.0a2"},
        "transport": transport,
        "date": "2026-11-13",
        "points": [
            {
                "property": name,
                "fingerprint": fingerprint,
                "read": "ok",
                "expected": "confirmed",
            }
            for name, fingerprint in modpoll_wot.point_fingerprints(model).items()
        ],
    }


def patch_upload(monkeypatch, uploaded):
    def fake_upload(report, *, timeout):
        uploaded["report"] = report
        return {"id": "p7n2d9x4k8m3q5ra"}

    monkeypatch.setattr(main, "_ensure_login", lambda: None)
    monkeypatch.setattr(verification, "upload_report", fake_upload)


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
    out = capsys.readouterr().out
    assert (
        "Group 2 of 3 (holding registers 10): exception code 02 (illegal data address).\n"
        "Group 3 of 3 (holding registers 20): no response.\n"
        "Not a full read: 2 of 4 points read.\n"
    ) in out
    assert "Only a full read can be uploaded." in out
    assert "Upload this report" not in out and "Continue?" not in out


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
    assert json.loads(out[out.index("{") : out.rindex("}") + 1])["reportVersion"] == 5


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
            "need --report",
        ),
        (["-f", "x.json", "--tcp", "x", "--yes"], "--yes needs --report or --upload"),
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
    assert modbus_task._read_options(args) == {"retries": 1}
    args.once = True
    assert modbus_task._read_options(args) == {"retries": 0}


def test_bare_report_interactively_saves_and_judges(monkeypatch, tmp_path, capsys):
    """--report without FILE asks where to save, whether the values look right and whether to upload."""
    path = write_model(tmp_path, three_group_model())
    monkeypatch.chdir(tmp_path)
    answers = iter(["y", "", "n"])  # values look right; default name; do not upload
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
    assert "Uploaded." not in capsys.readouterr().out


def test_bare_report_uploads_after_a_yes(monkeypatch, tmp_path, capsys):
    """A yes to the bare --report upload question shows the report and uploads it."""
    path = write_model(tmp_path, three_group_model())
    monkeypatch.chdir(tmp_path)
    answers = iter(["y", "", "y"])  # values look right; default name; upload
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))
    uploaded = {}
    patch_upload(monkeypatch, uploaded)
    run_app(
        monkeypatch,
        ["-f", str(path), "--tcp", "192.0.2.10", "--report"],
        FakeClient(False, False),
    )
    assert uploaded["report"]["reportVersion"] == 5
    out = capsys.readouterr().out
    assert "Report to upload:" in out
    assert "Uploaded." in out


def test_upload_only_sends_a_saved_report_without_a_read(monkeypatch, tmp_path, capsys):
    """--upload FILE uploads a saved report without a device or a --config."""
    report_path = tmp_path / "report-2026-11-13.json"
    report_path.write_text(
        json.dumps(saved_report(json.dumps(three_group_model()).encode()))
    )
    uploaded = {}
    patch_upload(monkeypatch, uploaded)
    with pytest.raises(SystemExit) as exit_info:
        run_app(monkeypatch, ["--upload", str(report_path), "--yes"], None)
    assert exit_info.value.code == 0
    assert uploaded["report"]["reportVersion"] == 5
    assert "Uploaded." in capsys.readouterr().out


def test_upload_only_picks_the_newest_report_interactively(monkeypatch, tmp_path):
    """Bare --upload offers the newest report-*.json as the default file."""
    model = json.dumps(three_group_model()).encode()
    old = tmp_path / "report-2026-11-11.json"
    old.write_text(json.dumps(saved_report(model, transport="rtu")))
    os.utime(old, (1_600_000_000, 1_600_000_000))
    new = tmp_path / "report-2026-11-13.json"
    new.write_text(json.dumps(saved_report(model)))
    monkeypatch.chdir(tmp_path)
    answers = iter(["", "y"])  # the offered default; upload
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))
    uploaded = {}
    patch_upload(monkeypatch, uploaded)
    with pytest.raises(SystemExit) as exit_info:
        run_app(monkeypatch, ["--upload"], None)
    assert exit_info.value.code == 0
    assert uploaded["report"]["transport"] == "tcp"


def test_upload_only_refuses_a_file_that_is_not_a_report(monkeypatch, tmp_path, caplog):
    bad = tmp_path / "report-2026-11-13.json"
    bad.write_text("{}")
    with pytest.raises(SystemExit) as exit_info:
        run_app(monkeypatch, ["--upload", str(bad), "--yes"], None)
    assert exit_info.value.code == 1
    assert "is not a verification report" in caplog.text


def test_upload_only_without_a_terminal_names_a_file(monkeypatch, tmp_path, caplog):
    with pytest.raises(SystemExit) as exit_info:
        run_app(monkeypatch, ["--upload"], None)
    assert exit_info.value.code == 1
    assert "Add --upload FILE" in caplog.text


def test_report_yes_saves_the_default_file_and_uploads(monkeypatch, tmp_path, capsys):
    """--report --yes is enough without a terminal: default file, then upload."""
    path = write_model(tmp_path, three_group_model())
    monkeypatch.chdir(tmp_path)
    uploaded = {}
    patch_upload(monkeypatch, uploaded)
    run_app(
        monkeypatch,
        ["-f", str(path), "--tcp", "192.0.2.10", "--report", "--yes"],
        FakeClient(False, False),
    )
    (saved,) = tmp_path.glob("report-*.json")
    assert uploaded["report"]["reportVersion"] == 5
    out = capsys.readouterr().out
    assert f"Report written to {saved.name}" in out
    assert "Uploaded." in out


def test_report_yes_without_a_login_fails_instead_of_signing_in(
    monkeypatch, tmp_path, caplog
):
    """--yes cannot answer the browser sign-in, so an upload needs an existing login."""
    path = write_model(tmp_path, three_group_model())
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MODIOHUB_CREDENTIALS", str(tmp_path / "credentials.json"))
    with pytest.raises(SystemExit) as exit_info:
        run_app(
            monkeypatch,
            ["-f", str(path), "--tcp", "192.0.2.10", "--report", "--yes"],
            FakeClient(False, False),
        )
    assert exit_info.value.code == 1
    assert "Sign in to" in caplog.text
    # The report is kept locally even though the upload did not run.
    assert list(tmp_path.glob("report-*.json"))


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


class ShortClient(FakeClient):
    """Address 10 does not answer, so group 3 is not tried; address 0 answers one register short."""

    def read_holding_registers(self, address, count, device_id):
        self.requests.append((address, count, device_id))
        if address == 10:
            return ModbusIOException("no response")
        return Answer(list(range(100, 100 + count - (address == 0))))


def test_failures_are_reported_as_the_device_answered(monkeypatch, tmp_path, capsys):
    """A decode failure names its point, and groups after a silent device are listed as not tried."""
    model = three_group_model()
    model["properties"]["ok1"]["forms"] = [raw_form("float32", 0)]
    model["properties"]["ok1"]["type"] = "number"
    del model["properties"]["ok2"]
    model["modpoll:acquisition"][0]["modpoll:members"] = ["ok1"]
    path = write_model(tmp_path, model)
    with pytest.raises(SystemExit) as exit_info:
        run_app(
            monkeypatch,
            ["-f", str(path), "--tcp", "x", "--report", str(tmp_path / "r.json")],
            ShortClient(),
        )
    assert exit_info.value.code == 1
    out = capsys.readouterr().out
    assert (
        "Point ok1 (group 1): the answer could not be decoded as float32.\n"
        "Group 2 of 3 (holding registers 10): no response.\n"
        "Group 3 of 3: not tried.\n"
        "Not a full read: 0 of 3 points read.\n"
    ) in out
    report = json.loads((tmp_path / "r.json").read_text())
    assert [p["read"] for p in report["points"]] == [
        "not-tested",
        "no-response",
        "not-tested",
    ]


def identity_model(meter_code):
    model = three_group_model()
    model["properties"]["ok1"]["const"] = meter_code
    return model


@pytest.mark.parametrize("meter_code, result", [(100, "match"), (7, "mismatch")])
def test_identity_points_are_compared_on_this_computer(
    monkeypatch, tmp_path, capsys, meter_code, result
):
    path = write_model(tmp_path, identity_model(meter_code))
    monkeypatch.chdir(tmp_path)
    uploaded = {}
    patch_upload(monkeypatch, uploaded)
    with pytest.raises(SystemExit) as exit_info:
        run_app(
            monkeypatch,
            ["-f", str(path), "--tcp", "x", "--report", "r.json", "--yes"],
            FakeClient(False, False),
        )
        raise SystemExit(0)
    report = json.loads((tmp_path / "r.json").read_text())
    assert report["reportVersion"] == 5
    assert report["points"][0]["identity"] == result
    assert all("identity" not in point for point in report["points"][1:])
    modpoll_wot.validate_report(report, model=path.read_bytes())
    out = capsys.readouterr().out
    if result == "match":
        assert exit_info.value.code == 0 and uploaded
    else:
        assert exit_info.value.code == 1 and not uploaded
        assert "Identity point ok1: read 100, the Thing Model expects 7." in out
        assert "may be a different product" in out


@pytest.mark.parametrize(
    "change, message",
    [
        (
            lambda r: r["points"][0].update(read="no-response"),
            "Not a full read: 3 of 4",
        ),
        (
            lambda r: r["points"][0].update(identity="mismatch"),
            "does not match the Thing Model",
        ),
        (lambda r: r.update(reportVersion=4), "older modpoll (report version 4)"),
    ],
)
def test_a_saved_report_that_cannot_be_uploaded_is_refused_here(
    monkeypatch, tmp_path, caplog, change, message
):
    model = json.dumps(identity_model(100)).encode()
    report = saved_report(model)
    report["points"][0]["identity"] = "match"
    change(report)
    if report["points"][0]["read"] != "ok":
        del report["points"][0]["identity"]
        report["points"][0]["expected"] = "unchecked"
    if report["reportVersion"] == 4:
        del report["points"][0]["identity"]
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report))
    uploaded = {}
    patch_upload(monkeypatch, uploaded)
    with pytest.raises(SystemExit) as exit_info:
        run_app(monkeypatch, ["--upload", str(path), "--yes"], None)
    assert exit_info.value.code == 1 and not uploaded
    assert message in caplog.text


def upload_saved(monkeypatch, tmp_path, matches, answers=(), report=None):
    report = report or saved_report(json.dumps(three_group_model()).encode())
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report))
    monkeypatch.setattr(verification, "matched_products", lambda r, *, timeout: matches)
    monkeypatch.setattr(
        verification,
        "search_products",
        lambda text, *, timeout: (
            [("acme/meter-2", "METER-2 (Acme)")] if text == "meter" else []
        ),
    )
    replies = iter(answers)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: bool(answers))
    monkeypatch.setattr("builtins.input", lambda prompt: next(replies))
    uploaded = {}
    patch_upload(monkeypatch, uploaded)
    with pytest.raises(SystemExit) as exit_info:
        run_app(
            monkeypatch, ["--upload", str(path), *([] if answers else ["--yes"])], None
        )
    return exit_info.value.code, uploaded.get("report")


def match(product, matched, exact=False):
    return {
        "productId": product,
        "matched": matched,
        "readablePoints": 4,
        "exact": exact,
    }


def test_a_report_with_a_product_is_uploaded_as_it_is(monkeypatch, tmp_path):
    report = saved_report(json.dumps(three_group_model()).encode())
    report["product"] = "acme/meter"
    code, sent = upload_saved(monkeypatch, tmp_path, [], report=report)
    assert code == 0 and sent["product"] == "acme/meter"


def test_an_exact_model_is_left_for_modiohub_to_identify(monkeypatch, tmp_path):
    code, sent = upload_saved(
        monkeypatch, tmp_path, [match("acme/meter", 4, exact=True)]
    )
    assert code == 0 and "product" not in sent


def test_points_that_all_belong_to_one_baseline_name_its_product(
    monkeypatch, tmp_path, capsys
):
    code, sent = upload_saved(monkeypatch, tmp_path, [match("acme/meter", 4)])
    assert code == 0 and sent["product"] == "acme/meter"
    assert (
        "Product: acme/meter (all 4 points are in its baseline Thing Model)."
        in capsys.readouterr().out
    )


def test_other_matches_are_chosen_interactively(monkeypatch, tmp_path, capsys):
    matches = [match("acme/meter", 3), match("acme/meter-2", 2)]
    code, sent = upload_saved(monkeypatch, tmp_path, matches, answers=["2", "y"])
    assert code == 0 and sent["product"] == "acme/meter-2"
    assert "acme/meter: 3 of 4 points match" in capsys.readouterr().out
    # Without a terminal there is nobody to choose.
    code, sent = upload_saved(monkeypatch, tmp_path, matches)
    assert code == 1 and sent is None


def test_without_a_match_a_search_or_a_catalog_request_follows(
    monkeypatch, tmp_path, capsys
):
    code, sent = upload_saved(monkeypatch, tmp_path, [], answers=["meter", "1", "y"])
    assert code == 0 and sent["product"] == "acme/meter-2"
    code, sent = upload_saved(monkeypatch, tmp_path, [], answers=["nothing", ""])
    assert code == 1 and sent is None
    out = capsys.readouterr().out
    assert "No product found." in out
    link = out[
        out.index("https://github.com/top-maker/open-modbus-catalog/issues/new?") :
    ].split()[0]
    body = urllib.parse.parse_qs(urllib.parse.urlsplit(link).query)["body"][0]
    assert "Model fingerprint: `mf1:" in body and "Points: 4" in body
    assert "100" not in body


@pytest.mark.parametrize(
    "code, message",
    [
        ("identity-missing", "Read them together with the other points."),
        ("not-full-read", "only a full read can be uploaded"),
        ("unknown-model", "Request the product in the catalog: https://github.com/"),
    ],
)
def test_a_refusal_is_explained_by_its_code(monkeypatch, code, message):
    class Refused:
        status_code, ok, headers = (
            422,
            False,
            {"Content-Type": "application/problem+json"},
        )

        def json(self):
            return {"code": code, "detail": "server text"}

    monkeypatch.setattr(
        verification.modpoll_wot,
        "load_session",
        lambda server: type("S", (), {"token": "t"}),
    )
    monkeypatch.setattr(verification.requests, "post", lambda *a, **k: Refused())
    report = saved_report(json.dumps(three_group_model()).encode())
    with pytest.raises(ValueError, match=re.escape(message)):
        verification.upload_report(report, timeout=3)
