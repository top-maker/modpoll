# Contributing to modsim

You can contribute a device model, correct one field, add a source or test result,
or improve the simulator. Small, focused contributions are welcome. You do not
need access to the website repository or a physical device to contribute a model.

## Choose the branch

`main` is the stable v1 line; `v2` is the model-driven development line. Target
**`v2` for the device-model contributions described here**, rather than accepting
the default PR target. Target the affected line for other fixes.

## Submit a device model with minimal paperwork

For a new model, submit one executable profile 0.2 Thing Model (TM):

```text
contrib/<vendor>/<model>/<model>.tm.json
```

In the PR description, provide:

- The manufacturer and model, unless already unambiguous in the TM or path.
- A public source link and relevant section/page, or an explanation of how you
  created the mapping. State the license or permission basis for submitted files;
  identify third-party material separately from your own work.
- Known limits: mapped functions/properties, firmware assumptions, and whether
  the model is documentation-derived, synthetic, or tested against hardware.
  Unknown firmware and untested hardware are acceptable; say so.
- Checks you actually ran and their results. If you could not run them, explain
  what remains for a maintainer to check.

Do not repeat information already present in a file; link to it. A correction PR
only needs the relevant change and its source or explanation. If you do not yet
have an executable model, open an issue with public references for discussion;
do not label it as a working model.

A device README, product photo, complete product metadata, simulation scenario,
and hardware evidence are **optional submission materials**. Maintainers can help
prepare the minimum documentation needed to publish the model. Missing photos or
hardware tests alone do not block consideration of a model.

You do not need to create catalog records, website indexes, generated TDs or
build artifacts for a new model. If additional information is necessary to judge
the mapping or permission to distribute a file, a maintainer may request it.

## Files and directory layout

Use lowercase kebab-case names for new vendor/model directories and new files.
Keep stable device paths when correcting an existing model. Existing conventional
names such as `README.md` and original third-party filenames may be retained.

```text
contrib/<vendor>/<model>/
  <model>.tm.json       # Required for a new executable model
  device.yaml          # Optional submission; maintainers can curate it here
  README.md            # Optional submission; maintainers can help complete it
  specs/               # Optional public reference material
  simulation/          # Optional local scenarios and behavior examples
  evidence/            # Optional test notes and attachments
  images/              # Optional images with source and permission information
```

Create optional directories only when needed. Prefer links to reference material
when you cannot establish permission to redistribute the files. Do not move an
existing model or rename an upstream document just to fit a new layout.

Keep register addresses, types, ordering and conversion rules in the TM as the
mapping source. Scenarios reference property names instead of maintaining another
register map. Describe partial coverage explicitly; do not present a subset as a
complete device implementation.

Human-maintained product metadata and evidence notes should use YAML or Markdown
where appropriate. Preserve JSON/JSON-LD for standard TM/TD files and upstream
originals. YAML comments explain decisions; facts, sources and unknown states
needed by consumers belong in fields. Quote model numbers and version strings;
avoid duplicate keys, custom tags and complex aliases.

Keep the optional `device.yaml` product record alongside the TM in the same
device directory. Contributors can follow other devices as examples, but do not
have to fill in this record: maintainers may help, including with AI assistance.
An approved record is maintained source data regardless of who drafted it. There
is no separate `catalog/` contribution tree. Website ingestion of these records
remains planned; the convention does not imply implemented schemas or ingestion.
Keep disposable indexes, pages and other build outputs outside device directories.

## Sources, images and private information

For an image, identify the exact model, original URL or author, permission/license
and any attribution requirements. A manufacturer image being publicly visible is
not, by itself, permission to redistribute it. If the basis is unclear, submit a
link for review rather than the image. Do not use generated illustrations as
photographic evidence of the device.

Do not include credentials, customer data, private endpoints or device serial
numbers in files, logs, screenshots or PR text. Review attachments as well as
structured fields before publishing. Mark redacted regions in evidence and do
not describe altered bytes as an untouched wire capture.

## Checks and evidence

Maintainers distinguish three evidence categories:

1. **L1 — configuration checks:** the stated TM/TD structure, Modbus binding and
   executable profile checks. This is not an official certification.
2. **L2 — software interoperability:** actual client/simulator communication,
   with exact versions, covered properties and expected results. Independent
   clients such as Eclipse Thingweb node-wot can cover only a documented subset.
3. **L3 — hardware communication:** requests and responses from a stated device,
   firmware and transport. Record unknown information and untested properties.

L2 or L3 is not required merely to propose a model. L1 and relevant regression
checks must be resolved before accepting it as an executable model; maintainers
can help run them. Existing CI success does not automatically test every model.

For evidence, record the model revision/hash, tool versions, commands, expected
and actual results, relevant attachments and limitations. A short Markdown or
YAML note is sufficient; no new report format or upload service is required.
Preserve failures and unsupported cases. Simulator interoperability does not
prove a real register map correct; hardware communication does not establish
engineering-unit accuracy or physical write behavior.

For a local model smoke test, adapt the documented
[one-device command](docs/site/model-validation.md#one-device) to the contributed TM.
Check initialization and a real client read; state the expected synthetic values
and stop the foreground simulator with Ctrl+C. Models can also be loaded from
fixed HTTPS URLs. Only models are fetched remotely; follow the documented local
file rules for scenarios and scripts.

For mapping changes, exercise the affected addresses/types/conversions and keep
expected values independent of the changed mapping where possible. Prefer
declarative scenarios. Custom Python behavior needs a repeatable example and
meaningful regression test; it runs locally only with explicit `--allow-scripts`.
See [model-driven simulation](docs/site/model-validation.md).

## How review works, including AI assistance

1. A contributor submits the model or focused correction and necessary context.
2. CI performs the configured deterministic checks. Maintainers review sources,
   compatibility, scope, evidence and distribution permissions.
3. Maintainers may use AI to propose descriptions, source references, YAML
   metadata, image candidates or review findings. Every added fact needs an
   inspectable source; unknowns stay unknown. AI does not approve its own changes,
   certify hardware or infer image permissions.
4. Maintainers review the resulting diff and rerun relevant checks. Necessary
   source/scope information is recorded in files before publication, in the same
   PR or a separate curation PR, rather than remaining only in comments.
5. A maintainer decides whether to merge. Model acceptance and website listing
   can happen separately while curation is completed.

Approved YAML metadata is maintained source data, not an AI output that may be
silently overwritten. Indexes, hashes, pages, thumbnails and TDs are generated by
deterministic tooling where implemented. Contributors do not hand-edit them.
For an existing checked-in generated fixture affected by a change, regenerate it
with the documented tool instead; do not require unrelated generated files in a
new-model PR. AI assistance does not require a new bot or automated workflow.

## Simulator development and broader checks

From the repository root:

```bash
git checkout v2
uv sync --all-groups
uv run pre-commit install
```

Run checks relevant to the change. A small source-link or wording correction does
not require a full simulator test matrix. For code or behavior changes, add
meaningful regression coverage and update documentation. Available checks are:

```bash
make check
make test
uv run python tools/generate-td.py --check
uv run mkdocs build -s -f mkdocs-preview.yml
uv run tox
```

The TD generator checks the existing fixtures it manages; it is not validation
of every contributed TM. The tox matrix covers Python 3.10 and 3.14 and requires
those interpreters. Record unavailable environments rather than claiming the full
matrix passed. Local protocol tests use loopback; physical device and serial
validation are separate. See [release process](docs/release-process.md) for
preview publishing; submitting a contribution does not require a release.

For bug reports, include a reproducible command, OS/Python and tool versions,
relevant model/scenario, and expected versus actual behavior. Use public or
redacted examples.
