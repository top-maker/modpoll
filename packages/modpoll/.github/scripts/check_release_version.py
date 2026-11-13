"""Reject a release if its tag and checked-out package metadata differ."""

import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib


def package_version():
    metadata = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    try:
        return metadata["project"]["version"]
    except KeyError as exc:
        raise ValueError("project version is missing from pyproject.toml") from exc


def main():
    tag = sys.argv[1]
    expected = tag[1:] if tag.startswith("v") else tag
    actual = package_version()
    if actual != expected:
        print(
            "Project version %s does not match release tag %s" % (actual, tag),
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
