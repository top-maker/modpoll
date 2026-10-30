# Contributing to modsim

Report issues with a reproducible command, OS/Python versions, relevant model or
scenario and expected versus actual behavior. Do not include credentials or
private device information.

## Development setup

Clone the repository, select the appropriate branch, and install dependencies:

```bash
git checkout v2
uv sync --all-groups
uv run pre-commit install
```

`main` is the stable v1 line while `v2` is the development line. Choose the PR
target for the affected line; do not assume the default branch contains v2.
Changes to a public model should include sources, licensing and verification
status; see [contrib](contrib/README.md).

## Checks

Run the relevant tests and quality checks before submitting:

```bash
make check
make test
uv run python tools/generate-td.py --check
uv run mkdocs build -s -f mkdocs-preview.yml
uv run tox
```

The tox matrix covers Python 3.10 and 3.14 and requires those interpreters. Record
unavailable environments rather than claiming the full matrix passed. Local
protocol tests use loopback; physical device and serial validation are separate.
Add meaningful regression coverage and update documentation for behavior changes.
See [release process](docs/release-process.md) for preview publishing.
