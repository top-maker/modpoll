"""Pinned consumer input integrity, containment and real runtime compilation."""

import hashlib
from importlib.util import module_from_spec, spec_from_file_location
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
spec = spec_from_file_location("fetch_models", ROOT / "tools/fetch-models.py")
fetch_models = module_from_spec(spec)
spec.loader.exec_module(fetch_models)


class Response(BytesIO):
    def geturl(self):
        return "https://example.invalid/model"


def test_verified_inputs_and_no_partial_write_on_bad_hash(tmp_path):
    payload = b"verified input"
    lock = {
        "repository": "example/models",
        "revision": "1" * 40,
        "files": {"vendor/model/model.tm.json": hashlib.sha256(payload).hexdigest()},
    }
    path = tmp_path / "source.yaml"
    path.write_text(yaml.safe_dump(lock))
    output = tmp_path / "out"
    with patch.object(
        fetch_models, "urlopen", return_value=Response(payload)
    ) as remote:
        fetch_models.fetch(path, output)
    assert "/" + "1" * 40 + "/" in remote.call_args.args[0]
    assert (output / "vendor/model/model.tm.json").read_bytes() == payload
    lock["files"]["other.tm.json"] = "0" * 64
    path.write_text(yaml.safe_dump(lock))
    with patch.object(
        fetch_models, "urlopen", side_effect=[Response(payload), Response(b"bad")]
    ):
        with pytest.raises(ValueError, match="hash mismatch"):
            fetch_models.fetch(path, tmp_path / "bad")
    assert not (tmp_path / "bad").exists()


@pytest.mark.parametrize(
    "revision,name",
    [("main", "model.tm.json"), ("1" * 40, "../escape"), ("1" * 40, "/absolute")],
)
def test_rejects_floating_revision_and_escaping_paths(tmp_path, revision, name):
    path = tmp_path / "source.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "repository": "example/models",
                "revision": revision,
                "files": {name: "0" * 64},
            }
        )
    )
    with patch.object(fetch_models, "urlopen") as remote:
        with pytest.raises(ValueError):
            fetch_models.fetch(path, tmp_path / "out")
    remote.assert_not_called()


def test_pinned_catalog_deployment_compiles_when_prepared():
    from modsim.manifest import load_deployment

    if not (ROOT / "examples/models").exists():
        pytest.skip("Run tools/fetch-models.py to prepare pinned public inputs")
    deployment = load_deployment(ROOT / "examples/deployment.yaml")
    runtimes = [
        item.build(allow_scripts=False) for item in deployment.instances.values()
    ]
    assert len(runtimes) == 2
