"""Metadata contract tests: structure, safe YAML, and a dedicated CLI path."""

from copy import deepcopy
import subprocess
import sys

import pytest
import yaml

from modpoll_wot.metadata import (
    device_schema,
    load_device_record,
    validate_device_record,
)
from modpoll_wot.validation import ModelValidationError


@pytest.fixture
def record():
    return {
        "schema-version": "1",
        "id": "example-vendor/example-model",
        "vendor": "Example Vendor",
        "model": "Example Model",
        "firmware": None,
        "models": [{"path": "example-model.tm.json"}],
        "sources": [
            {
                "url": "https://example.com/manual",
                "locator": "section 3",
                "basis": "documentation-derived",
            }
        ],
        "redistribution": {"model-license": "MIT", "reference-files": "link-only"},
    }


def test_metadata_contract_and_cli(record, tmp_path):
    assert device_schema()["properties"]["schema-version"]["const"] == "1"
    validate_device_record(record)
    path = tmp_path / "device.yaml"
    path.write_text(yaml.safe_dump(record))
    assert load_device_record(path) == record
    run = subprocess.run(
        [sys.executable, "-m", "modpoll_wot", "validate-device", str(path)],
        capture_output=True,
        text=True,
    )
    assert run.returncode == 0, run.stderr
    assert "not a mapping or hardware check" in run.stdout


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema-version", 1),
        ("firmware", 123),
        ("id", "../bad"),
        ("models", [{"path": "../outside.tm.json"}]),
        (
            "sources",
            [{"url": "javascript:alert(1)", "locator": "x", "basis": "synthetic"}],
        ),
        ("unexpected", True),
    ],
)
def test_invalid_metadata_is_rejected(record, field, value):
    record[field] = value
    with pytest.raises(ModelValidationError):
        validate_device_record(record)


@pytest.mark.parametrize(
    "prefix",
    [
        "id: duplicate\n",
        "value: &anchor text\nother: *anchor\n",
        "value: !custom text\n",
    ],
)
def test_unsafe_yaml_is_rejected(record, prefix, tmp_path):
    path = tmp_path / "device.yaml"
    path.write_text(prefix + yaml.safe_dump(record))
    with pytest.raises(ModelValidationError):
        load_device_record(path)
    run = subprocess.run(
        [sys.executable, "-m", "modpoll_wot", "validate-device", str(path)],
        capture_output=True,
        text=True,
    )
    assert run.returncode == 1


def test_missing_source_is_not_inferred(record):
    incomplete = deepcopy(record)
    del incomplete["sources"]
    with pytest.raises(ModelValidationError):
        validate_device_record(incomplete)
