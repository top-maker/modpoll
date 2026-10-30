"""Preview release gates must enforce the current CI matrix."""

import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "preview_guard",
    Path(__file__).resolve().parents[1] / ".github/scripts/preview-release.py",
)
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


def test_guard_requires_all_current_ci_jobs(monkeypatch):
    monkeypatch.setenv("GITHUB_REPOSITORY", "example/modsim")
    monkeypatch.setattr(release.subprocess, "run", lambda *a, **kw: None)
    jobs = [
        {"name": name, "conclusion": "success"}
        for name in ("quality", "docs", "tox (3.10)", "tox (3.14)")
    ]

    def output(args, **kwargs):
        if args[:3] == ["git", "rev-parse", "HEAD"]:
            return "candidate\n"
        if "runs?head_sha=" in " ".join(args):
            return json.dumps(
                {
                    "workflow_runs": [
                        {
                            "head_branch": "v2",
                            "status": "completed",
                            "conclusion": "success",
                            "id": 42,
                        }
                    ]
                }
            )
        return json.dumps({"jobs": jobs})

    monkeypatch.setattr(release.subprocess, "check_output", output)
    release.guard("v2.0.0a1")
    jobs.pop()
    with pytest.raises(ValueError, match="expected CI jobs"):
        release.guard("v2.0.0a1")
    jobs.append({"name": "tox (3.14)", "conclusion": "failure"})
    with pytest.raises(ValueError, match="expected CI jobs"):
        release.guard("v2.0.0a1")


def test_download_waits_for_pypi_and_checks_wheel_hash(monkeypatch, tmp_path, capsys):
    import hashlib
    import io
    import urllib.error

    content = b"published wheel"
    item = {
        "filename": "package.whl",
        "url": "https://files.pythonhosted.org/package.whl",
        "digests": {"sha256": hashlib.sha256(content).hexdigest()},
    }
    clock = [0]
    metadata_calls = []
    urls = []
    monkeypatch.setattr(release.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(
        release.time, "sleep", lambda seconds: clock.__setitem__(0, clock[0] + seconds)
    )
    monkeypatch.setattr(release.time, "time_ns", lambda: clock[0])

    def metadata(version):
        metadata_calls.append(version)
        if len(metadata_calls) <= 8:
            return None
        return {"urls": [] if len(metadata_calls) == 9 else [item]}

    def fetch(url, timeout):
        urls.append(url)
        if len(urls) == 1:
            raise urllib.error.HTTPError(url, 404, "not ready", {}, None)
        return io.BytesIO(content)

    monkeypatch.setattr(release, "metadata", metadata)
    monkeypatch.setattr(release.urllib.request, "urlopen", fetch)
    release.download("2.0.0a2", tmp_path)
    assert (tmp_path / "package.whl").read_bytes() == content
    assert len(metadata_calls) == 10 and len(urls) == 2 and urls[0] != urls[1]
    assert clock[0] == 200
    assert "retrying" in capsys.readouterr().err
    item["digests"]["sha256"] = "wrong"
    with pytest.raises(ValueError, match="SHA256 mismatch"):
        release.download("2.0.0a2", tmp_path)


def test_pypi_retry_times_out_and_does_not_hide_other_errors(monkeypatch):
    import urllib.error

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
