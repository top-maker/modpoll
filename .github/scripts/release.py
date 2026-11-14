"""Release checks for the three packages of this repository (standard library only).

Every command takes the release tag, `<package>-v<version>` (for example `modsim-v2.0.0a14`):

    release.py version TAG [--root DIR]   the tag matches the package metadata
    release.py guard TAG                  version, commit on v2 and every required CI check succeeded
    release.py pypi TAG                   PyPI has no files for the version yet, or exactly these files
    release.py download TAG --directory DIR   wait for the published wheel and verify its digest

The commands work from any directory: package paths are relative to the repository root.
"""

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib

ROOT = Path(__file__).resolve().parents[2]
PREVIEW = r"2\.[0-9]+\.[0-9]+(?:a|b|rc)[0-9]+"
ANY = r"[0-9]+\.[0-9]+\.[0-9]+(?:(?:a|b|rc)[0-9]+)?"
INTEGRATION = "integration conformance"


@dataclass(frozen=True)
class Package:
    directory: str
    versions: str
    # The check runs that must have succeeded on the release commit, by name. Job names are unique
    # across the repository's workflows; test_release.py proves each one is a job that exists.
    checks: frozenset
    module: str | None = None

    def path(self, root=ROOT):
        return Path(root) / self.directory


PACKAGES = {
    "modpoll": Package(
        "packages/modpoll",
        PREVIEW,
        frozenset(
            {
                "quality-check",
                "tox (3.10)",
                "tox (3.14)",
                "docs",
                "modsim-equivalence",
                INTEGRATION,
            }
        ),
    ),
    "modsim": Package(
        "packages/modsim",
        PREVIEW,
        frozenset(
            {
                "modsim quality",
                "modsim docs",
                "modsim tox (3.10)",
                "modsim tox (3.14)",
                "modpoll snapshot replay",
                "catalog-interop",
                "single-device (ubuntu-latest)",
                "single-device (macos-latest)",
                "single-device (windows-latest)",
                INTEGRATION,
            }
        ),
        module="modsim/__init__.py",
    ),
    "modpoll-wot": Package(
        "packages/modpoll-wot",
        ANY,
        frozenset(
            {
                "modpoll-wot test (3.10)",
                "modpoll-wot test (3.14)",
                "modpoll-wot package",
                "consumer (modpoll)",
                "consumer (modsim)",
                INTEGRATION,
            }
        ),
    ),
}


def parse_tag(tag):
    """Return the package name, its definition and the version a release tag names."""
    for name in sorted(PACKAGES, key=len, reverse=True):
        prefix = f"{name}-v"
        if tag.startswith(prefix):
            version = tag[len(prefix) :]
            if re.fullmatch(PACKAGES[name].versions, version):
                return name, PACKAGES[name], version
            raise ValueError(
                f"{tag}: {version} is not a version {name} releases from v2"
            )
    raise ValueError(
        f"{tag}: expected <package>-v<version> for one of {sorted(PACKAGES)}"
    )


def check_version(tag, root=ROOT):
    """The tag must name the version in pyproject.toml and, where there is one, the module."""
    name, package, version = parse_tag(tag)
    directory = package.path(root)
    metadata = tomllib.loads((directory / "pyproject.toml").read_text(encoding="utf-8"))
    declared = metadata.get("project", {}).get("version")
    if declared != version:
        raise ValueError(f"{tag}: {name} declares version {declared}")
    if package.module:
        text = (directory / package.module).read_text(encoding="utf-8")
        found = re.search(r'^__version__ = "([^"]+)"', text, re.M)
        if not found or found.group(1) != version:
            raise ValueError(f"{tag}: {package.module} declares another version")
    return name, package, version


def require_checks(package, runs, sha):
    """Use the newest run of each name, so a rerun can neither hide nor repair the wrong commit."""
    latest = {}
    for run in runs:
        if run["name"] not in latest or run["id"] > latest[run["name"]]["id"]:
            latest[run["name"]] = run
    missing = sorted(
        name
        for name in package.checks
        if latest.get(name, {}).get("head_sha") != sha
        or latest[name].get("conclusion") != "success"
    )
    if missing:
        raise ValueError(
            "release commit lacks successful checks: " + ", ".join(missing)
        )


def get_json(url, token=None):
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def check_runs(sha):
    api = os.environ.get("GITHUB_API_URL", "https://api.github.com")
    repository = os.environ["GITHUB_REPOSITORY"]
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    runs, page = [], 1
    while True:
        data = get_json(
            f"{api}/repos/{repository}/commits/{sha}/check-runs?per_page=100&page={page}",
            token,
        )
        runs += data["check_runs"]
        if len(runs) >= data["total_count"] or not data["check_runs"]:
            return runs
        page += 1


def guard(tag):
    name, package, version = check_version(tag)
    sha = (
        os.environ.get("GITHUB_SHA")
        or subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, cwd=ROOT
        ).strip()
    )
    subprocess.run(
        ["git", "merge-base", "--is-ancestor", sha, "origin/v2"], check=True, cwd=ROOT
    )
    require_checks(package, check_runs(sha), sha)
    print(f"Accepted {name} {version} at {sha}")


def local_artifacts(directory):
    artifacts = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in Path(directory).iterdir()
        if path.is_file()
        and (path.name.endswith(".whl") or path.name.endswith(".tar.gz"))
    }
    if len(artifacts) != 2 or sum(name.endswith(".whl") for name in artifacts) != 1:
        raise ValueError("exactly one wheel and one sdist are required")
    return artifacts


def pypi_state(name, version, artifacts, fetch=get_json):
    """`absent` when PyPI has no such version, `identical` when it holds exactly these files."""
    try:
        data = fetch(
            f"https://pypi.org/pypi/{name}/{version}/json?cache_bust={time.time_ns()}"
        )
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return "absent"
        raise
    published = {item["filename"]: item["digests"]["sha256"] for item in data["urls"]}
    if published != artifacts:
        raise ValueError(
            f"PyPI already holds {name} {version} with other files; "
            "publish the original artifacts or a new version"
        )
    return "identical"


def wait_for(fetch, label, deadline, sleep=time.sleep, clock=time.monotonic):
    """Retry a resource PyPI may not serve yet, without masking any other failure."""
    attempts = 0
    while True:
        attempts += 1
        try:
            value = fetch()
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                raise
            value = None
        if value is not None:
            return value
        remaining = deadline - clock()
        if remaining <= 0:
            raise TimeoutError(
                f"PyPI {label} still unavailable after {attempts} attempts"
            )
        delay = min(20, remaining)
        print(
            f"PyPI {label} not available yet; retrying in {delay:.0f}s",
            file=sys.stderr,
            flush=True,
        )
        sleep(delay)


def download_wheel(name, version, directory, fetch=get_json, read=None):
    """Wait up to ten minutes for the published wheel and verify its digest."""
    deadline = time.monotonic() + 600

    def find_wheel():
        data = fetch(
            f"https://pypi.org/pypi/{name}/{version}/json?cache_bust={time.time_ns()}"
        )
        wheels = [item for item in data["urls"] if item["filename"].endswith(".whl")]
        if len(wheels) > 1:
            raise ValueError("expected exactly one published wheel")
        return wheels[0] if wheels else None

    item = wait_for(find_wheel, "wheel metadata", deadline)

    def fetch_wheel():
        separator = "&" if "?" in item["url"] else "?"
        with urllib.request.urlopen(
            f"{item['url']}{separator}cache_bust={time.time_ns()}", timeout=60
        ) as response:
            return response.read()

    content = wait_for(read or fetch_wheel, "wheel file", deadline)
    if hashlib.sha256(content).hexdigest() != item["digests"]["sha256"]:
        raise ValueError("downloaded wheel does not match PyPI's SHA-256")
    destination = Path(directory) / item["filename"]
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(content)
    return destination


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=("version", "guard", "pypi", "download"))
    parser.add_argument("tag")
    parser.add_argument(
        "--root", type=Path, default=ROOT, help="checkout to read (version)"
    )
    parser.add_argument(
        "--directory", type=Path, help="where to save the wheel (download)"
    )
    args = parser.parse_args(argv)
    if args.command == "version":
        name, _, version = check_version(args.tag, args.root)
        print(f"{name} {version}")
    elif args.command == "guard":
        guard(args.tag)
    elif args.command == "pypi":
        name, package, version = check_version(args.tag)
        state = pypi_state(name, version, local_artifacts(package.path() / "dist"))
        if "GITHUB_OUTPUT" in os.environ:
            with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
                output.write(f"state={state}\n")
        print(f"PyPI {name} {version}: {state}")
    else:
        if not args.directory:
            parser.error("download requires --directory")
        name, _, version = parse_tag(args.tag)
        print(download_wheel(name, version, args.directory))


if __name__ == "__main__":
    main()
