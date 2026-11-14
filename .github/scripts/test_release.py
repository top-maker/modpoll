"""The release checks every package's release workflow runs (.github/scripts/release.py)."""

import hashlib
import importlib.util
import io
import itertools
from pathlib import Path
import shutil
import urllib.error

import pytest
import yaml

spec = importlib.util.spec_from_file_location(
    "release", Path(__file__).with_name("release.py")
)
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)

WORKFLOWS = release.ROOT / ".github/workflows"


def job_names():
    """Every check name the repository's workflows produce, with matrix values expanded."""
    names = []
    for path in sorted(WORKFLOWS.glob("*.yml")):
        for key, job in yaml.safe_load(path.read_text())["jobs"].items():
            name = job.get("name", key)
            matrix = job.get("strategy", {}).get("matrix", {})
            rows = (
                matrix.get("include")
                or [
                    dict(zip(matrix, values))
                    for values in itertools.product(
                        *(v for v in matrix.values() if isinstance(v, list))
                    )
                ]
                or [{}]
            )
            for row in rows:
                expanded = name
                for field, value in row.items():
                    expanded = expanded.replace("${{ matrix.%s }}" % field, str(value))
                names.append((expanded, path.name))
    return names


def test_job_names_are_unique_across_workflows():
    # The guard finds checks by name; a second job with the same name could stand in for it.
    seen = {}
    for name, workflow in job_names():
        assert name not in seen, f"{name!r} in both {seen.get(name)} and {workflow}"
        seen[name] = workflow


@pytest.mark.parametrize("package", sorted(release.PACKAGES))
def test_every_required_check_is_a_job(package):
    names = {name for name, _ in job_names()}
    assert release.PACKAGES[package].checks <= names
    assert "${{" not in " ".join(release.PACKAGES[package].checks)


def test_tags_name_their_package_and_a_version_it_releases():
    assert release.parse_tag("modpoll-v2.0.0a12")[::2] == ("modpoll", "2.0.0a12")
    assert release.parse_tag("modsim-v2.0.0a14")[::2] == ("modsim", "2.0.0a14")
    # The longest package name wins: this is modpoll-wot, not modpoll.
    assert release.parse_tag("modpoll-wot-v0.7.0a1")[::2] == ("modpoll-wot", "0.7.0a1")
    assert release.parse_tag("modpoll-wot-v1.0.0")[::2] == ("modpoll-wot", "1.0.0")
    for tag in (
        "v2.0.0a12",
        "modpoll-v1.6.2",
        "modsim-v2.0.0",
        "modsim-v2.0.0a1-extra",
        "other-v1.0.0",
    ):
        with pytest.raises(ValueError):
            release.parse_tag(tag)


def test_the_tag_must_match_the_package_metadata():
    for name, package in release.PACKAGES.items():
        version = release.tomllib.loads(
            (package.path() / "pyproject.toml").read_text()
        )["project"]["version"]
        assert release.check_version(f"{name}-v{version}")[::2] == (name, version)
    with pytest.raises(ValueError, match="declares version"):
        release.check_version("modsim-v2.9.9a1")


def test_modsim_must_also_declare_the_version_in_its_module(tmp_path):
    package = release.PACKAGES["modsim"]
    target = package.path(tmp_path)
    (target / "modsim").mkdir(parents=True)
    shutil.copy(package.path() / "pyproject.toml", target)
    version = release.tomllib.loads((target / "pyproject.toml").read_text())["project"][
        "version"
    ]
    (target / package.module).write_text('__version__ = "2.0.0a1"\n')
    with pytest.raises(ValueError, match="modsim/__init__.py"):
        release.check_version(f"modsim-v{version}", tmp_path)
    (target / package.module).write_text(f'__version__ = "{version}"\n')
    release.check_version(f"modsim-v{version}", tmp_path)


def run(name, run_id, conclusion="success", sha="abc"):
    return {"name": name, "id": run_id, "conclusion": conclusion, "head_sha": sha}


def test_every_required_check_must_have_succeeded_on_the_commit():
    package = release.PACKAGES["modpoll-wot"]
    passing = [run(name, index) for index, name in enumerate(sorted(package.checks))]
    release.require_checks(package, passing, "abc")
    with pytest.raises(ValueError, match="consumer \\(modsim\\)"):
        release.require_checks(
            package, [r for r in passing if r["name"] != "consumer (modsim)"], "abc"
        )
    with pytest.raises(ValueError, match="lacks successful checks"):
        release.require_checks(package, passing, "other")
    # The newest run of a name decides: a later failure is not hidden by an earlier success,
    # and a later success after a failure is accepted.
    with pytest.raises(ValueError, match="modpoll-wot package"):
        release.require_checks(
            package, passing + [run("modpoll-wot package", 99, "failure")], "abc"
        )
    retried = passing[:-1] + [
        run(passing[-1]["name"], 50, "failure"),
        run(passing[-1]["name"], 51),
    ]
    release.require_checks(package, retried, "abc")


def not_found():
    return urllib.error.HTTPError(
        "https://pypi.org", 404, "Not Found", {}, io.BytesIO()
    )


def test_pypi_holds_nothing_or_exactly_the_built_files(tmp_path):
    (tmp_path / "pkg-1.0-py3-none-any.whl").write_bytes(b"wheel")
    (tmp_path / "pkg-1.0.tar.gz").write_bytes(b"sdist")
    local = release.local_artifacts(tmp_path)

    def missing(url):
        raise not_found()

    assert release.pypi_state("pkg", "1.0", local, fetch=missing) == "absent"
    published = {
        "urls": [{"filename": n, "digests": {"sha256": d}} for n, d in local.items()]
    }
    assert (
        release.pypi_state("pkg", "1.0", local, fetch=lambda url: published)
        == "identical"
    )
    other = {"urls": [{"filename": "pkg-1.0.tar.gz", "digests": {"sha256": "0" * 64}}]}
    with pytest.raises(ValueError, match="other files"):
        release.pypi_state("pkg", "1.0", local, fetch=lambda url: other)
    (tmp_path / "pkg-1.0-py3-none-any.whl").unlink()
    with pytest.raises(ValueError, match="one wheel and one sdist"):
        release.local_artifacts(tmp_path)


def test_waiting_retries_only_what_pypi_does_not_serve_yet():
    answers = iter([None, not_found(), "ready"])

    def fetch():
        answer = next(answers)
        if isinstance(answer, Exception):
            raise answer
        return answer

    clock = itertools.count()
    assert (
        release.wait_for(
            fetch, "x", 100, sleep=lambda s: None, clock=lambda: next(clock)
        )
        == "ready"
    )

    def refused():
        raise urllib.error.HTTPError(
            "https://pypi.org", 403, "Forbidden", {}, io.BytesIO()
        )

    with pytest.raises(urllib.error.HTTPError, match="403"):
        release.wait_for(refused, "x", 100, sleep=lambda s: None)
    with pytest.raises(TimeoutError):
        release.wait_for(lambda: None, "x", 0, sleep=lambda s: None, clock=lambda: 1)


def test_a_downloaded_wheel_must_match_pypis_digest(tmp_path):
    content = b"the wheel"
    item = {
        "filename": "pkg-1.0-py3-none-any.whl",
        "url": "https://files.example/pkg.whl",
        "digests": {"sha256": hashlib.sha256(content).hexdigest()},
    }
    data = {"urls": [item]}
    saved = release.download_wheel(
        "pkg", "1.0", tmp_path, fetch=lambda url: data, read=lambda: content
    )
    assert saved.read_bytes() == content
    with pytest.raises(ValueError, match="SHA-256"):
        release.download_wheel(
            "pkg", "1.0", tmp_path, fetch=lambda url: data, read=lambda: b"tampered"
        )
