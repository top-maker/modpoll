"""Reject a release if its tag and checked-out package metadata differ."""

import re
import sys
from pathlib import Path


def package_version():
    section = ""
    for line in Path("pyproject.toml").read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            section = stripped
        elif section == "[tool.poetry]":
            match = re.fullmatch(
                r'version\s*=\s*["\']([^"\']+)["\']\s*(?:#.*)?', stripped
            )
            if match:
                return match.group(1)
    raise ValueError("project version is missing from pyproject.toml")


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
