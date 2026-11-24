# modpoll, modsim and modpoll-wot

- Review the working tree and current branch before editing. Keep unrelated changes out of a commit.
- Commit messages follow Conventional Commits; pull request titles use the types checked by the `validate` workflow.
- Run `mise run gitleaks` (a full-history secret scan, also run in CI) before opening a pull request. Allowlist a gitleaks false positive in `.gitleaks.toml` by its fingerprint only.
- Package tests and the documentation build are described in `README.md`; each package keeps its own `Makefile`.

## Git workflow exception

This repository's base branch is `v2`, not `develop`. `main` is the 1.6.x maintenance line, and the CI and release workflows (and `release.py`) hardcode `v2`. Create feature branches from `v2` and merge them back into `v2`; wherever the shared rules say `develop`, read `v2`. Never modify or push `main` directly. This exception ends when `v2` is merged into `main`; the workspace registration of the `v2` base branch is removed at the same time.
