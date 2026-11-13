"""Wheel metadata must stay portable regardless of a developer's environment."""

import importlib.util
from pathlib import Path
import zipfile

import pytest

spec = importlib.util.spec_from_file_location(
    "portable_wheel",
    Path(__file__).resolve().parents[1] / ".github/scripts/check-portable-wheel.py",
)
wheel = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wheel)


@pytest.mark.parametrize(
    "requirement,valid",
    [
        ("modpoll-wot (==0.2.0a1)", True),
        ("modpoll-wot (>=0.1)", False),
        ("modpoll-wot @ file:///home/developer/core", False),
        (
            "modpoll-wot (==0.2.0a1)\nRequires-Dist: other @ https://example.org/source.zip",
            False,
        ),
    ],
)
def test_release_wheel_rejects_path_dependencies_and_floating_core(
    tmp_path, requirement, valid
):
    path = tmp_path / "app.whl"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "modpoll-2.0.0a2.dist-info/METADATA",
            "Name: modpoll\nVersion: 2.0.0a2\nRequires-Dist: " + requirement + "\n",
        )
    if valid:
        wheel.check(path)
    else:
        with pytest.raises(ValueError):
            wheel.check(path)
