"""Modsim preview guards and immutable registry verification (standard library)."""

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


def metadata(version):
    url = f"https://pypi.org/pypi/modsim/{version}/json?release_check={time.time_ns()}"
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise


def guard(tag):
    if not re.fullmatch(r"v2\.\d+\.\d+(?:a|b|rc)\d+", tag):
        raise ValueError("expected a unique v2 prerelease tag")
    subprocess.run(
        [sys.executable, ".github/scripts/check_release_version.py", tag], check=True
    )
    actual = re.search(
        r'__version__ = "([^"]+)"', Path("modsim/__init__.py").read_text()
    ).group(1)
    if actual != tag[1:]:
        raise ValueError("module version differs from release tag")
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    subprocess.run(["git", "merge-base", "--is-ancestor", sha, "origin/v2"], check=True)
    repo = os.environ["GITHUB_REPOSITORY"]
    listing = json.loads(
        subprocess.check_output(
            [
                "gh",
                "api",
                f"repos/{repo}/actions/workflows/main.yml/runs?head_sha={sha}&event=push&per_page=100",
            ],
            text=True,
        )
    )
    runs = [run for run in listing["workflow_runs"] if run["head_branch"] == "v2"]
    if (
        not runs
        or runs[0]["status"] != "completed"
        or runs[0]["conclusion"] != "success"
    ):
        raise ValueError("exact release SHA requires successful v2 CI")
    jobs = json.loads(
        subprocess.check_output(
            [
                "gh",
                "api",
                f"repos/{repo}/actions/runs/{runs[0]['id']}/jobs?per_page=100",
            ],
            text=True,
        )
    )["jobs"]
    expected = {"quality", "docs"} | {
        f"tox ({version})" for version in ("3.10", "3.14")
    }
    if {job["name"] for job in jobs} != expected or any(
        job["conclusion"] != "success" for job in jobs
    ):
        raise ValueError("release requires all four expected CI jobs")
    print(f"Accepted {sha} from CI {runs[0]['id']}")


def immutable(version):
    data = metadata(version)
    if data is None:
        result = "false"
    else:
        published = {
            item["filename"]: item["digests"]["sha256"] for item in data["urls"]
        }
        local = {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in Path("dist").iterdir()
            if p.is_file()
        }
        if local != published:
            raise ValueError(
                "immutable PyPI version already exists with different bytes; recover original artifacts"
            )
        result = "true"
    with open(os.environ["GITHUB_OUTPUT"], "a") as output:
        output.write(f"exists={result}\n")


def download(version, directory):
    # Avoid a stale simple index immediately after successful publication.
    data = None
    for attempt in range(6):
        data = metadata(version)
        if data is not None:
            break
        time.sleep(5)
    if data is None:
        raise ValueError("published version is not available in PyPI metadata")
    item = next(item for item in data["urls"] if item["filename"].endswith(".whl"))
    with urllib.request.urlopen(item["url"], timeout=30) as response:
        payload = response.read()
    if hashlib.sha256(payload).hexdigest() != item["digests"]["sha256"]:
        raise ValueError("published wheel SHA256 mismatch")
    destination = Path(directory)
    destination.mkdir(parents=True, exist_ok=True)
    (destination / item["filename"]).write_bytes(payload)
    print(item["filename"], item["digests"]["sha256"])


if __name__ == "__main__":
    command, version = sys.argv[1:3]
    if command == "guard":
        guard(version)
    elif command == "immutable":
        immutable(version)
    elif command == "download":
        download(version, sys.argv[3])
    else:
        raise ValueError("unknown command")
