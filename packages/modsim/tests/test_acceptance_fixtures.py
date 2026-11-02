"""Detached fixture preparation must preserve the original repository path base."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from unittest.mock import Mock

import yaml

spec = spec_from_file_location(
    "prepare_acceptance",
    Path(__file__).resolve().parents[1] / "tools/prepare-acceptance.py",
)
prepare_acceptance = module_from_spec(spec)
spec.loader.exec_module(prepare_acceptance)


def test_relocated_manifest_preserves_model_and_scenario_base(tmp_path, monkeypatch):
    directory = tmp_path / "examples"
    directory.mkdir()
    (directory / "model-source.yaml").write_text("revision: pinned\n")
    manifest = directory / "deployment.yaml"
    manifest.write_text(
        yaml.safe_dump(
            {
                "devices": [
                    {
                        "model": "examples/models/vendor/model.tm.json",
                        "scenario": "examples/models/vendor/initial.sim.json",
                    }
                ]
            }
        )
    )
    fetch = Mock()
    monkeypatch.setattr(prepare_acceptance.subprocess, "run", fetch)
    prepare_acceptance.prepare(tmp_path)
    args = fetch.call_args.args[0]
    assert str(directory / "model-source.yaml") in args
    assert str(directory / "models") in args
    device = yaml.safe_load(manifest.read_text())["devices"][0]
    assert device["model"] == str(directory / "models/vendor/model.tm.json")
    assert device["scenario"] == str(directory / "models/vendor/initial.sim.json")


def test_historical_release_is_left_unchanged(tmp_path, monkeypatch):
    fetch = Mock()
    monkeypatch.setattr(prepare_acceptance.subprocess, "run", fetch)
    prepare_acceptance.prepare(tmp_path)
    fetch.assert_not_called()
