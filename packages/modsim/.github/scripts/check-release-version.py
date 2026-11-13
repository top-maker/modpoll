"""Reject releases when the CLI version differs from the release tag."""

import ast
import sys
from pathlib import Path

from check_release_version import package_version


def main():
    tag = sys.argv[1]
    expected = tag[1:] if tag.startswith("v") else tag
    package = package_version()
    if package != expected:
        print(
            "Project version %s does not match release tag %s" % (package, tag),
            file=sys.stderr,
        )
        return 1
    module = ast.parse(Path("modsim/__init__.py").read_text(encoding="utf-8"))
    versions = [
        node.value.value
        for node in module.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "__version__"
            for target in node.targets
        )
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    ]
    if versions != [expected]:
        print(
            "modsim CLI version does not match release tag %s (found %s)"
            % (tag, versions),
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
