# Preview release process

Stable release-please stays on main. A v2 prerelease uses a unique PEP 440 version
and `v2.*` tag from v2, with matching pyproject and module versions. Push the
candidate first and wait for all seven main CI jobs (quality, docs, five Python
versions). The preview guard requires successful CI on that exact SHA and v2
ancestry before publishing.

`preview.yml` checks out the tag, saves original wheel/sdist artifacts, verifies
installation and immutable registry hashes, publishes PyPI and a GitHub prerelease,
then the explicit version Docker image and documentation under `/v2/`. Stable
Docker and GitHub latest are not advanced. The preview Pages deployment preserves
the stable documentation; stable-line Pages maintenance should retain `/v2/`.

Acceptance installs the published wheel with SHA verification, runs model/runtime
protocol tests without application source, and checks the published container's
two-device deployment. Do not mark a release accepted until all jobs pass. Record
SHA/tag, run URL, registry hashes and acceptance results in the project log.
Never replace tags or PyPI versions. If a later job fails, retry that failed job;
if publication itself needs recovery, reuse the original saved distributions.

Registry acceptance waits up to ten minutes in total for version metadata and
the wheel, retrying HTTP 404 and missing wheel metadata with fresh cache-busting
URLs. Other HTTP errors and hash mismatches fail immediately. If the wait times
out, keep the original artifacts for recovery; do not replace a tag or version.

To repeat acceptance for an existing immutable tag after fixing validation tools,
run the preview workflow manually on v2 with its `tag` input. This skips all
publishing jobs, installs the existing PyPI wheel, uses fixtures from that exact
tag and runs the current acceptance tooling. It does not replace packages or
images. Record the separate validation run and tooling SHA.
