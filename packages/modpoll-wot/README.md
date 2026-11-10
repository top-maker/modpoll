# modpoll-wot (experimental)

An independently versioned TM/TD configuration interpreter for
[Modpoll](https://github.com/top-maker/modpoll),
[Modsim](https://github.com/top-maker/modsim) and future compatible consumers.
No Modbus execution, scheduler or MQTT service is included.

Releases up to `0.2.0a4` were developed in the Modpoll repository under
`packages/modpoll-wot`; this repository keeps that history and tags them as `v<version>`.

The existing TM CLI is available in `modpoll-wot==0.2.0a2`.
Version `0.3.0a3` removes the `modpoll:audit` plan; a full read uses `modpoll:acquisition`.
Version `0.3.0a2` renames verification report fields to `product` and `chassis` (schema 2).
Version `0.3.0a1` adds point and model fingerprints and the verification report schema,
and removes the device metadata schema; see [CONTRACT.md](CONTRACT.md).

```sh
modpoll-wot new --title "meter"
modpoll-wot validate meter.tm.json
modpoll-wot validate meter.tm.json --kind tm --profile
modpoll-wot export meter.tm.json --host 127.0.0.1 --port 5020 --unit-id 7 -o meter.td.json
modpoll-wot validate meter.td.json
modpoll-wot fingerprint meter.tm.json
modpoll-wot validate-report report.json --model meter.tm.json
```

Use `modpoll-wot --help` and `modpoll-wot validate --help` for options.
Validation reports each check separately with a tick or cross and an error
detail on failure. Terminal markers are colored; redirected output has no ANSI
colors, and `NO_COLOR` disables colors. The exit status is zero only on success.
Structure validation is offline and rejects duplicate JSON keys; it does not
check JSON-LD, references, device behavior or complete W3C conformance. Type is
detected from the document, so use `--kind tm` for a known TM whose type might
be missing. `--profile` checks the executable subset, accepting instance options
and `--param NAME=JSON` when needed. `new` writes `<title>.tm.json` in the current directory by default; use `-o`
to choose another path. It never overwrites a file. The starter is a standard TM skeleton;
add profile 0.2 mappings before executable validation or export. Export accepts
`--target node-wot-0.9.2` for the documented subset and never overwrites files.

See [profile.md](profile.md) for the current profile and
[CONTRACT.md](CONTRACT.md) for the profile 0.2-only execution policy.

The loader validates bundled W3C TM/TD 1.1 schemas, the project extension
schema, and acquisition semantics. It does not execute Modbus requests.

```python
from modpoll_wot.loading import load_model
model = load_model("meter.tm.json", unit_id=1)
```

## Development

Install [mise](https://mise.jdx.dev/installing-mise.html), then run the source
tests, build the wheel and sdist, and smoke-test the installed wheel:

```sh
mise trust
mise install
mise run check
```

The bundled W3C schemas identify themselves as 1.1-12-March-2025, retrieved from
https://www.w3.org/2022/wot/td-schema/v1.1 and
https://www.w3.org/2022/wot/tm-schema/v1.1. Standard validation does not
establish device correctness.

Version 0.2.0a1 supports [profile 0.2](profile.md): standard Form mappings,
explicit blocks, per-property decoding and TM-to-TD export. Current development
source rejects profile 0.1. This compatibility removal is not yet published; use
a new immutable release version when promoting it, then update consumer pins.

## Releases

Released versions and tags are immutable.

1. On `main`, set `version` in `pyproject.toml` to a new version and merge it
   through a pull request whose CI passes, including the consumer job.
2. Push the tag `v<version>` at that commit. The release workflow checks the
   tag, tests and builds, publishes to PyPI, verifies the registry installation
   and records a GitHub prerelease with the built files.
3. Update the exact `modpoll-wot` pin in each consumer repository in its own
   pull request.

A failed publish never replaces an existing version: rerun the failed job, or
release a new version.
