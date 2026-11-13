import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "release_image_tags",
    Path(__file__).resolve().parents[1] / ".github/scripts/release_image_tags.py",
)
tags = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tags)


def releases(*versions):
    return [
        {"tag_name": "v" + version, "draft": False, "prerelease": False}
        for version in versions
    ]


def test_latest_release_updates_all_matching_aliases():
    assert tags.select_tags("v2.1.0", releases("1.8.9", "2.0.0", "2.1.0")) == (
        ["2.1.0", "2", "2.1", "latest"],
        True,
    )


def test_maintenance_release_does_not_replace_newer_major():
    assert tags.select_tags("v1.8.1", releases("1.7.9", "1.8.1", "2.0.0")) == (
        ["1.8.1", "1", "1.8"],
        False,
    )


def test_old_patch_does_not_replace_major_or_minor_aliases():
    assert tags.select_tags("v1.8.0", releases("1.8.0", "1.8.1", "2.0.0")) == (
        ["1.8.0"],
        False,
    )


def test_draft_prerelease_and_unknown_tag_cannot_publish_aliases():
    data = releases("1.0.0") + [
        {"tag_name": "v3.0.0", "draft": True},
        {"tag_name": "v4.0.0", "prerelease": True},
    ]
    assert tags.select_tags("v1.0.0", data)[0][-1] == "latest"
    for tag in ("v1.1.0", "v1.0.0-rc1", "bad"):
        with pytest.raises(ValueError):
            tags.select_tags(tag, data)


def test_older_minor_only_updates_its_own_minor_alias():
    assert tags.select_tags("v1.8.2", releases("1.8.2", "1.9.0", "2.0.0")) == (
        ["1.8.2", "1.8"],
        False,
    )


def test_package_version_guard_accepts_matching_tag_and_rejects_mismatch():
    import subprocess
    import sys
    import re

    root = Path(__file__).resolve().parents[1]
    guard = root / ".github/scripts/check_release_version.py"
    source = (root / "pyproject.toml").read_text()
    current = re.search(r'^version = "([^" ]+)"', source, re.MULTILINE).group(1)
    for tag, expected in (("v" + current, 0), ("v9.9.9", 1)):
        result = subprocess.run(
            [sys.executable, str(guard), tag], cwd=root, capture_output=True, text=True
        )
        assert result.returncode == expected
        if expected:
            assert "does not match" in result.stderr


def test_release_listing_fetches_all_pages(monkeypatch):
    import io
    import json

    monkeypatch.setenv("GITHUB_API_URL", "https://api.example.test")
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GH_TOKEN", "test-token")
    calls = []
    first_page = releases(*["1.0.%d" % i for i in range(100)])
    second_page = releases("2.0.0")

    def fake_open(request, timeout):
        calls.append((request.full_url, timeout))
        return io.BytesIO(
            json.dumps(first_page if len(calls) == 1 else second_page).encode()
        )

    monkeypatch.setattr(tags.urllib.request, "urlopen", fake_open)
    result = tags.fetch_releases()
    assert len(result) == 101
    assert calls[0][0].endswith("page=1")
    assert calls[1][0].endswith("page=2")
    assert tags.select_tags("v1.0.99", result) == (["1.0.99", "1", "1.0"], False)


def test_release_selection_emits_image_names_and_latest_flag(
    monkeypatch, tmp_path, capsys
):
    monkeypatch.setattr(tags, "fetch_releases", lambda: releases("1.2.0", "2.0.0"))
    output = tmp_path / "github-output"
    for key, value in {
        "TAG": "v1.2.0",
        "DOCKER_REGISTRY": "registry.example",
        "DOCKER_USERNAME": "team",
        "IMAGE_NAME": "modpoll",
        "GITHUB_OUTPUT": str(output),
    }.items():
        monkeypatch.setenv(key, value)
    tags.main()
    assert capsys.readouterr().out.splitlines() == [
        "registry.example/team/modpoll:1.2.0",
        "registry.example/team/modpoll:1",
        "registry.example/team/modpoll:1.2",
    ]
    assert output.read_text() == "latest=false\n"
