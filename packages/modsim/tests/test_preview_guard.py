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
