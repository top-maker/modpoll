"""Audit uses precise read spans and reports each sample."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import modpoll_wot

from modpoll import audit
from modpoll.arg_parser import get_parser

pytestmark = pytest.mark.skipif(
    not hasattr(modpoll_wot, "AuditPlan"),
    reason="requires the audit producer candidate or release",
)
FIXTURE = Path(__file__).resolve().parent / "fixtures/numeric.tm.json"


@pytest.mark.parametrize("failed", [False, True])
def test_audit_reads_selected_points_over_serial(tmp_path, monkeypatch, capsys, failed):
    source = json.loads(FIXTURE.read_bytes())
    source["modpoll:audit"] = {"status": ["measurement", "counter"]}
    file = tmp_path / "audit.tm.json"
    file.write_text(json.dumps(source))
    args = get_parser().parse_args(
        ["--audit", "-f", str(file), "--serial", "test-port", "--unit-id", "9"]
    )
    reads = []

    def read(address, *, count, device_id):
        reads.append((address, count, device_id))
        return SimpleNamespace(
            isError=lambda: failed and address == 40004,
            registers=[0x3FC0, 0] if count == 2 else [287],
        )

    def connect(options):
        assert options.serial == "test-port" and options.audit
        return SimpleNamespace(
            connect=lambda: True, close=lambda: None, read_holding_registers=read
        )

    monkeypatch.setattr(audit, "_create_modbus_client", connect)
    assert audit.run_audit(args) == int(failed)
    report = json.loads(capsys.readouterr().out)
    assert report["identity_result"] == "not-provided"
    assert [row["value"] for row in report["status"]] == [
        None if failed else 1.5,
        287,
    ]
    assert reads == [(40004, 2, 9), (40000, 1, 9)]


def test_audit_rejects_missing_plan_before_connecting(monkeypatch):
    args = get_parser().parse_args(["--audit", "-f", str(FIXTURE), "--tcp", "test"])
    monkeypatch.setattr(
        audit, "_create_modbus_client", lambda _: pytest.fail("connected")
    )
    with pytest.raises(ValueError, match="requires a modpoll:audit plan"):
        audit.run_audit(args)
