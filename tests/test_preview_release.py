"""Release gates must reject wrong routes, stale CI and differing registry bytes."""

import hashlib
import io
import importlib.util
from pathlib import Path
import urllib.error

import pytest

spec = importlib.util.spec_from_file_location(
    "preview_release",
    Path(__file__).resolve().parents[1] / ".github/scripts/preview-release.py",
)
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


def test_release_routes_do_not_accept_stable_tags_or_other_packages():
    assert release.release_target("v2.0.0a2")[:2] == ("modpoll", "2.0.0a2")
    assert release.release_target("modpoll-wot-v0.2.0a1")[:2] == (
        "modpoll-wot",
        "0.2.0a1",
    )
    for tag in ("v1.6.2", "v2.0.0", "v2.0.0a1-extra", "other-v0.1.0a1"):
        with pytest.raises(ValueError):
            release.release_target(tag)


def test_release_gate_requires_same_sha_and_latest_success_for_every_job():
    checks = [
        {"id": i, "name": name, "head_sha": "candidate", "conclusion": "success"}
        for i, name in enumerate(release.CHECKS)
    ]
    release.require_checks(checks, "candidate")
    for invalid in (
        checks[:-1],
        checks + [dict(checks[0], id=100, conclusion="failure")],
        [dict(c, head_sha="old") for c in checks],
    ):
        with pytest.raises(ValueError):
            release.require_checks(invalid, "candidate")


def test_registry_retries_require_exact_original_filenames_and_hashes(
    monkeypatch, tmp_path
):
    wheel, sdist = tmp_path / "package.whl", tmp_path / "package.tar.gz"
    wheel.write_bytes(b"wheel")
    sdist.write_bytes(b"sdist")
    files = [wheel, sdist]
    data = {
        "urls": [
            {
                "filename": p.name,
                "digests": {"sha256": hashlib.sha256(p.read_bytes()).hexdigest()},
            }
            for p in files
        ]
    }
    sidecar = tmp_path / ".gitignore"
    sidecar.write_text("*\n")
    files.append(sidecar)
    requests = []

    def get_json(url):
        requests.append(url)
        return data

    monkeypatch.setattr(release, "get_json", get_json)
    assert release.pypi_state("package", "0.1a1", files) == "identical"
    assert "cache_bust=" in requests[-1]
    wheel.write_bytes(b"different build")
    with pytest.raises(ValueError, match="differs"):
        release.pypi_state("package", "0.1a1", files)
    with pytest.raises(ValueError, match="wheel and one sdist"):
        release.pypi_state("package", "0.1a1", [wheel])


def test_registry_outage_is_not_treated_as_an_unused_version(monkeypatch, tmp_path):
    files = [tmp_path / "package.whl", tmp_path / "package.tar.gz"]
    for path in files:
        path.write_bytes(b"artifact")

    def error(code):
        def fetch(url):
            raise urllib.error.HTTPError(url, code, "unavailable", {}, None)

        return fetch

    monkeypatch.setattr(release, "get_json", error(404))
    assert release.pypi_state("package", "0.1a1", files) == "absent"
    monkeypatch.setattr(release, "get_json", error(503))
    with pytest.raises(urllib.error.HTTPError):
        release.pypi_state("package", "0.1a1", files)


def test_downloaded_wheel_matches_pypi_metadata(monkeypatch, tmp_path):
    content = b"published wheel"
    data = {
        "urls": [
            {
                "filename": "package-0.2-py3-none-any.whl",
                "url": "https://files.pythonhosted.org/package.whl",
                "digests": {"sha256": hashlib.sha256(content).hexdigest()},
            }
        ]
    }
    monkeypatch.setattr(release, "get_json", lambda url: data)
    monkeypatch.setattr(
        release.urllib.request,
        "urlopen",
        lambda url, timeout: io.BytesIO(content),
    )
    wheel = release.download_published_wheel("package", "0.2", tmp_path)
    assert wheel.read_bytes() == content

    data["urls"][0]["digests"]["sha256"] = "wrong"
    with pytest.raises(ValueError, match="SHA-256"):
        release.download_published_wheel("package", "0.2", tmp_path)


def test_pypi_propagation_retries_metadata_and_wheel(monkeypatch, tmp_path, capsys):
    content = b"published wheel"
    item = {
        "filename": "package.whl",
        "url": "https://files.pythonhosted.org/package.whl",
        "digests": {"sha256": hashlib.sha256(content).hexdigest()},
    }
    clock = [0]
    urls = []
    downloads = []
    monkeypatch.setattr(release.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(
        release.time, "sleep", lambda seconds: clock.__setitem__(0, clock[0] + seconds)
    )
    monkeypatch.setattr(release.time, "time_ns", lambda: clock[0])

    def metadata(url):
        urls.append(url)
        if len(urls) <= 8:
            raise urllib.error.HTTPError(url, 404, "not yet visible", {}, None)
        return {"urls": [] if len(urls) == 9 else [item]}

    def download(url, timeout):
        downloads.append(url)
        if len(downloads) == 1:
            raise urllib.error.HTTPError(url, 404, "not yet visible", {}, None)
        return io.BytesIO(content)

    monkeypatch.setattr(release, "get_json", metadata)
    monkeypatch.setattr(release.urllib.request, "urlopen", download)
    assert (
        release.download_published_wheel("package", "0.2", tmp_path).read_bytes()
        == content
    )
    assert len(urls) == 10 and len(set(urls)) == 10
    assert len(downloads) == 2 and len(set(downloads)) == 2
    assert clock[0] == 200
    assert "retrying" in capsys.readouterr().err


def test_pypi_retry_timeout_and_other_errors(monkeypatch):
    clock = [0]
    monkeypatch.setattr(release.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(
        release.time, "sleep", lambda seconds: clock.__setitem__(0, clock[0] + seconds)
    )
    with pytest.raises(TimeoutError, match="metadata still unavailable"):
        release._wait_for_pypi(lambda: None, "metadata", 45)
    assert clock[0] == 45

    def forbidden():
        raise urllib.error.HTTPError("https://example.org", 403, "forbidden", {}, None)

    with pytest.raises(urllib.error.HTTPError, match="403"):
        release._wait_for_pypi(forbidden, "metadata", 600)
    assert clock[0] == 45
