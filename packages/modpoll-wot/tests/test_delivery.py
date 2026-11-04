"""Regression tests for the public TM boundary and point-table projection."""

from hashlib import sha256
import json
from pathlib import Path

import pytest

from modpoll_wot import (
    AcquisitionError,
    derive_audit_tm,
    loads_model,
    project_point_table,
)


def source_document():
    fixture = Path(__file__).parent / "fixtures/numeric.tm.json"
    return json.loads(fixture.read_bytes())


def test_public_tm_projects_only_exact_approved_read_spans():
    source = source_document()
    source["title"] = "Private title"
    source["modpoll:audit"] = {"identity": ["counter"], "status": ["measurement"]}
    counter = source["properties"]["counter"]
    counter.update(readOnly=False, description="Internal note", unit="Private unit")
    counter["forms"][0]["op"] = ["readproperty", "writeproperty"]
    for prop in source["properties"].values():
        form = prop["forms"][0]
        address, quantity = form["modv:address"], form["modv:quantity"]
        form["href"] = (
            f"modbus+tcp://private.example:1502/9/{address}?quantity={quantity}"
        )
        form["modv:unitID"] = 9
    payload = json.dumps(source).encode()
    artifact = derive_audit_tm(payload, title="Approved device")
    public = artifact.payload

    assert artifact == derive_audit_tm(payload, title="Approved device")
    assert artifact.source_sha256 == sha256(payload).hexdigest()
    assert artifact.sha256 == sha256(public).hexdigest()
    for secret in (
        b"Private title",
        b"Internal note",
        b"Private unit",
        b"private.example",
        b"unitID",
        b"writeproperty",
    ):
        assert secret not in public

    model = loads_model(public)
    assert model.endpoint is None
    assert model.audit.identity == ("counter",)
    assert model.audit.status == ("measurement",)
    assert [(g.start, g.quantity) for g in model.groups] == [(40000, 1), (40004, 2)]

    rows = project_point_table(public)
    full_rows = project_point_table(payload)
    assert [row["property"] for row in full_rows] == [
        "counter",
        "signed",
        "measurement",
    ]
    assert full_rows[0]["writable"] and full_rows[0]["unit"] == "Private unit"
    assert [(r["property"], r["address"], r["quantity"]) for r in rows] == [
        ("counter", 40000, 1),
        ("measurement", 40004, 2),
    ]
    assert all(r["read_function_code"] == 3 and not r["writable"] for r in rows)


def test_derivation_requires_a_reviewable_audit_selection():
    payload = json.dumps(source_document()).encode()
    with pytest.raises(AcquisitionError, match="requires a modpoll:audit plan"):
        derive_audit_tm(payload, title="Approved device")
