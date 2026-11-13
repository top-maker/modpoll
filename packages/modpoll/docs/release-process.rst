Preview release process
=======================

The ``modpoll-wot`` interpreter is developed and released from its own
repository, `top-maker/modpoll-wot <https://github.com/top-maker/modpoll-wot>`_.
It validates bundled WoT TD/TM 1.1 schemas and the Modpoll executable profile
0.2; it is not a device execution service. Its CI runs this repository's test
suite against each candidate wheel before release.

1. On ``v2``, select a candidate whose exact commit passes quality, Python
   3.10/3.11/3.12, documentation and simulator interoperability CI.
2. To adopt a new interpreter, wait until its release is installable from
   PyPI, then pin that exact version in ``pyproject.toml`` and refresh the lock
   in a pull request. Build wheel/sdist and Docker; the wheel guard rejects
   source URLs and non-exact interpreter requirements.
3. The application release does not require an interpreter release.
4. Verify the application candidate and push ``v2.0.0a2`` at that accepted SHA.
   ``preview-app.yml`` publishes the application, an explicit amd64/arm64 image,
   versioned documentation and runs registry-installed acceptance with no
   application source directory. Previews never move stable Docker aliases.
5. Check PyPI, GitHub Release assets, both image manifests and Pages URLs.
   Record commit/tag, workflow links, checksums and acceptance results.

Tag pushes route releases using the workflow stored at that tag; every checkout
explicitly selects the tag. The v1 release-please flow remains on ``main``.
The preview guard rejects stable tags and tags other than ``v2`` previews. Never replace an existing tag or PyPI version.
Retries compare artifact filenames and SHA-256 against PyPI; different bytes
require the original artifacts or a new version, not an overwrite. Retain workflow
artifacts if a later publishing stage fails and rerun only failed jobs.

After publication, registry acceptance waits up to ten minutes in total for
the version metadata and wheel to become visible, retrying HTTP 404 and missing
wheel metadata with changing query strings, which do not guarantee a cache
bypass. Other HTTP errors and SHA-256 mismatches fail immediately. A timeout remains a failure; retain the original
build artifacts for recovery rather than replacing the tag or release.

Pages uses serialized complete snapshots. ``1.x/`` and ``v2/`` coexist, root
continues serving stable documentation, and ``vocab/`` is preserved independently.
The initial 1.x tree is built from the pinned v1.6.1 release. Subsequent stable
releases update their line while preserving other directories; PRs only build.
No preview is considered fully accepted until the published-package acceptance
job succeeds. See `validation <validation.rst>`_ for the published preview acceptance and
maintainer-confirmed Eastron physical RS485 result.
