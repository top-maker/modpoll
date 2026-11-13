# Preview release process

Stable release-please stays on main. A v2 prerelease uses a unique PEP 440 version
and `v2.*` tag from v2, with matching pyproject and module versions. Push the
candidate first and wait for all four main CI jobs (quality, docs, Python 3.10 and 3.14). The preview guard requires successful CI on that exact SHA and v2
ancestry before publishing. Catalog/platform acceptance must also pass on that
exact v2 SHA: independent installed-wheel Linux/macOS/Windows single-device
checks and the catalog-interop job.

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
the wheel, retrying HTTP 404 and missing wheel metadata with changing query
strings, which do not guarantee a cache bypass. Other HTTP errors and hash
mismatches fail immediately. If the wait times
out, keep the original artifacts for recovery; do not replace a tag or version.

To repeat acceptance for an existing immutable tag after fixing validation tools,
run the preview workflow manually on v2 with its `tag` input. This skips all
publishing jobs, installs the existing PyPI wheel, uses fixtures from that exact
tag and runs the current acceptance tooling. It does not replace packages or
images. Record the separate validation run and tooling SHA.

### Known-value checks

Use the approved TM as the configuration for a local TCP simulator. Seed known
values with `--initial PROPERTY=JSON` or `--data` with an `initial` object, then read them with
a full modpoll read. Thing Models no longer carry a `modpoll:audit` plan; a
full read covers every property in `modpoll:acquisition`.

Stop a foreground simulator with Ctrl-C. Restart with the same TM and initial
values to restore the original vector. A managed deployment can use
`modsim down -f deployment.yaml` and `modsim up -f deployment.yaml` on POSIX.
These checks verify software interoperability with the selected fixture.
