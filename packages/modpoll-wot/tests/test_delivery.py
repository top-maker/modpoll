"""Regression tests for the point-table projection."""

from pathlib import Path

import pytest

from modpoll_wot import AcquisitionError, point_fingerprints, project_point_table

FIXTURE = Path(__file__).parent / "fixtures/numeric.tm.json"


def test_point_table_follows_acquisition_order_with_fingerprints():
    payload = FIXTURE.read_bytes()
    rows = project_point_table(payload)
    fingerprints = point_fingerprints(payload)

    assert [(r["property"], r["address"], r["quantity"]) for r in rows] == [
        ("counter", 40000, 1),
        ("signed", 40002, 1),
        ("measurement", 40004, 2),
    ]
    assert all(r["read_function_code"] == 3 and not r["writable"] for r in rows)
    assert {r["property"]: r["fingerprint"] for r in rows} == fingerprints


def test_point_table_rejects_instance_descriptions():
    td = (FIXTURE.parent / "modsim.generated.td.json").read_bytes()
    with pytest.raises(AcquisitionError, match="require a project Thing Model"):
        project_point_table(td)
