"""Point fingerprints and verification report contract."""

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

import pytest

from modpoll_wot import (
    ReportError,
    export_td,
    model_fingerprint,
    point_fingerprints,
    validate_report,
)
from modpoll_wot.profile import instantiate
from modpoll_wot.verification import canonical_point, fingerprint

FIXTURES = Path(__file__).parent / "fixtures"
NUMERIC = FIXTURES / "numeric.tm.json"


def numeric():
    return json.loads(NUMERIC.read_bytes())


def test_shared_vectors_pin_the_canonical_encoding():
    vectors = json.loads((FIXTURES / "modsim.fingerprints.json").read_bytes())
    _, effective = instantiate(json.loads((FIXTURES / vectors["model"]).read_bytes()))
    for name, expected in vectors["points"].items():
        point = canonical_point(effective["properties"][name])
        canonical = json.dumps(
            point, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
        assert canonical == expected["canonical"]
        assert fingerprint(point) == expected["fingerprint"]
        assert (
            expected["fingerprint"]
            == "pf1:" + sha256(canonical.encode()).hexdigest()
        )
    payload = (FIXTURES / vectors["model"]).read_bytes()
    assert vectors["points"].keys() == point_fingerprints(payload).keys()
    unique = sorted({point["fingerprint"] for point in vectors["points"].values()})
    encoded = json.dumps(unique, separators=(",", ":")).encode()
    assert vectors["fingerprint"] == "mf1:" + sha256(encoded).hexdigest()
    assert model_fingerprint(payload) == vectors["fingerprint"]


def test_instance_data_and_spelling_do_not_change_fingerprints():
    source = numeric()
    baseline = point_fingerprints(source)
    td = export_td(source, host="192.0.2.10", port=1502, unit_id=7)
    assert point_fingerprints(td) == baseline

    edited = numeric()
    props = edited["properties"]
    props["total"] = props.pop("counter")
    props["total"]["description"] = "Renamed in a fork"
    props["total"]["unit"] = "count"
    edited["modpoll:acquisition"][0]["modpoll:members"][0] = "total"
    form = props["signed"]["forms"][0]
    form["modv:mostSignificantByte"] = True
    form["modv:mostSignificantWord"] = True
    edited["title"] = "Forked pilot"
    edited["description"] = "Cosmetic fork"
    edited["modpoll:acquisition"][0]["modpoll:members"].reverse()
    renamed = point_fingerprints(edited)
    assert renamed["total"] == baseline["counter"]
    assert renamed["signed"] == baseline["signed"]
    assert model_fingerprint(edited) == model_fingerprint(source)
    assert model_fingerprint(td) == model_fingerprint(source)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("modv:address", 40003),
        ("modv:type", "xsd:unsignedShort"),
        ("modv:mostSignificantByte", False),
    ],
)
def test_mapping_changes_split_fingerprints(field, value):
    source = numeric()
    source["properties"]["signed"]["forms"][0][field] = value
    if field == "modv:type":
        source["properties"]["signed"]["minimum"] = 0
    assert point_fingerprints(source)["signed"] != point_fingerprints(numeric())["signed"]
    assert model_fingerprint(source) != model_fingerprint(numeric())


def test_multiplier_is_compared_as_a_decimal():
    def with_multiplier(value):
        source = numeric()
        source["properties"]["measurement"]["forms"][0]["modpoll:multiplier"] = value
        return point_fingerprints(source)["measurement"]

    assert with_multiplier(0.1) == with_multiplier("0.10") == with_multiplier("1E-1")
    assert with_multiplier(100) == with_multiplier("1e2")
    assert with_multiplier(0.1) != with_multiplier(0.01)


def test_write_only_points_have_no_fingerprint():
    source = numeric()
    prop = source["properties"]["counter"]
    prop.pop("readOnly")
    prop["writeOnly"] = True
    prop["forms"][0]["op"] = "writeproperty"
    assert "counter" not in point_fingerprints(source)


def test_adding_or_removing_a_readable_point_changes_the_model_fingerprint():
    source = numeric()
    del source["properties"]["signed"]
    source["modpoll:acquisition"][0]["modpoll:members"].remove("signed")
    assert model_fingerprint(source) != model_fingerprint(numeric())


def report_for(payload):
    prints = point_fingerprints(payload)
    return {
        "reportVersion": 1,
        "device": "example/numeric-pilot",
        "model": {
            "sha256": sha256(payload).hexdigest(),
            "fingerprint": model_fingerprint(payload),
            "source": "catalog",
            "ref": "f" * 40,
            "path": "models/numeric-pilot.tm.json",
        },
        "tool": {"name": "modpoll", "version": "2.1.0a1", "interpreter": "0.3.0a1"},
        "transport": "tcp",
        "date": "2026-11-09",
        "environment": {"firmware": "A2.15", "configuration": "range 0x07 on AI0"},
        "points": [
            {
                "property": "counter",
                "fingerprint": prints["counter"],
                "read": "ok",
                "expected": "confirmed",
            },
            {
                "property": "signed",
                "fingerprint": prints["signed"],
                "read": "exception",
                "exceptionCode": 2,
                "expected": "unchecked",
            },
        ],
    }


def test_a_report_validates_against_its_exact_model():
    payload = NUMERIC.read_bytes()
    report = report_for(payload)
    validate_report(report)
    validate_report(report, model=payload)

    other = json.dumps(numeric()).encode()
    with pytest.raises(ReportError, match="/model/sha256"):
        validate_report(report, model=other)

    stale = deepcopy(report)
    stale["model"]["fingerprint"] = "mf1:" + "0" * 64
    with pytest.raises(ReportError, match="/model/fingerprint"):
        validate_report(stale, model=payload)

    forked = deepcopy(report)
    forked["points"][0]["fingerprint"] = "pf1:" + "0" * 64
    with pytest.raises(ReportError, match="/points/0/fingerprint"):
        validate_report(forked, model=payload)

    unknown = deepcopy(report)
    unknown["points"][0]["property"] = "missing"
    with pytest.raises(ReportError, match="no readable property missing"):
        validate_report(unknown, model=payload)


def mutate(path, value):
    report = report_for(NUMERIC.read_bytes())
    *parents, key = path
    target = report
    for part in parents:
        target = target[part]
    if value is KeyError:
        del target[key]
    else:
        target[key] = value
    return report


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("host",), "192.0.2.10"),
        (("environment", "serialNumber"), "SN123"),
        (("points", 0, "value"), 12),
        (("points", 1, "exceptionCode"), KeyError),
        (("points", 0, "exceptionCode"), 2),
        (("points", 1, "expected"), "confirmed"),
        (("points", 0, "fingerprint"), "sha256:" + "0" * 64),
        (("model", "ref"), KeyError),
        (("model", "fingerprint"), KeyError),
        (("model", "fingerprint"), "pf1:" + "0" * 64),
        (("model", "ref"), "main"),
        (("device",), "Example/Numeric"),
        (("date",), "2026-11-09T10:00:00Z"),
        (("points",), []),
    ],
)
def test_reports_reject_private_or_inconsistent_fields(path, value):
    with pytest.raises(ReportError):
        validate_report(mutate(path, value))


def test_model_source_rules():
    workspace = mutate(("model", "source"), "workspace")
    with pytest.raises(ReportError):
        validate_report(workspace)
    del workspace["model"]["path"]
    workspace["model"]["ref"] = "fork-3"
    validate_report(workspace)

    local = mutate(("model", "source"), "local")
    with pytest.raises(ReportError):
        validate_report(local)
    del local["model"]["path"], local["model"]["ref"]
    validate_report(local)


def test_duplicate_points_are_rejected():
    report = report_for(NUMERIC.read_bytes())
    report["points"].append(dict(report["points"][0]))
    with pytest.raises(ReportError, match="duplicate properties"):
        validate_report(report)


def test_cli_fingerprints_and_validates_reports(tmp_path):
    def cli(*args):
        return subprocess.run(
            [sys.executable, "-m", "modpoll_wot", *map(str, args)],
            capture_output=True,
            text=True,
        )

    printed = cli("fingerprint", NUMERIC)
    assert printed.returncode == 0
    assert json.loads(printed.stdout) == {
        "model": model_fingerprint(NUMERIC.read_bytes()),
        "points": point_fingerprints(NUMERIC.read_bytes()),
    }

    report = tmp_path / "report.json"
    report.write_text(json.dumps(report_for(NUMERIC.read_bytes())))
    checked = cli("validate-report", report, "--model", NUMERIC)
    assert checked.returncode == 0, checked.stderr
    assert "hash and fingerprints" in checked.stdout

    report.write_text(json.dumps(mutate(("host",), "192.0.2.10")))
    rejected = cli("validate-report", report)
    assert rejected.returncode == 1
    assert "Additional properties" in rejected.stderr


def test_fixture_report_matches_its_model():
    report = json.loads((FIXTURES / "numeric.report.json").read_bytes())
    assert report == report_for(NUMERIC.read_bytes())
