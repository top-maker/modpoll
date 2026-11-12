# Executable configuration contract 0.2

Current development source executes only documents declaring
`"modpoll:version": "0.2"`. Profile 0.1, missing versions and unknown versions
are rejected by model loading, instantiation, export and executable validation.
Standard-only TM/TD schema validation is separate and does not promise execution.

[profile.md](profile.md) is the mapping/API specification. The maintained source
is a TM; a TD is an instantiated input or export artifact. Both use standard
property DataSchemas and Modbus Forms for raw types, addresses, quantities,
access, units and ordering. Acquisition groups list property names and explicit
request blocks. Bit-table offsets count physical bits, not eight-bit groups.

To migrate an old profile, move member decoding metadata into property Forms,
keep request boundaries and holes, convert bit-table member offsets to physical
addresses, and derive Unit ID consistently from Forms/instance arguments.
Changing only the version string is insufficient. Preserve known input/output
vectors and revalidate the result; there is no implicit legacy conversion.

Retained float16, packed-bit and register boolean codecs are explicit profile
0.2 features, not profile 0.1 document support. Their semantics and third-party
export limits remain documented in the profile.

The profile 0.1 loader, Forms validator, schema and acceptance fixtures have
been removed. Shared member/type checks validate profile 0.2 directly. The
37-property example and independent vectors continue to cover values, requests,
access rules, aliases, ordering and conversions.

This source change does not rewrite existing release artifacts or the exact
registry dependencies of consumers. Before release, allocate a new immutable
shared-package version, test independent installation and consumer interoperability,
publish the producer first, and only then change consumer pins. Package version
and executable profile version are distinct. Existing profile 0.2 semantics are
preserved; removing the older executable input does not redefine profile 0.2.

## Version 0.4.0a1

Version 0.4.0a1 adds [simulation data](profile.md#simulation-data): schema
`simulation-data-1.json`, `load_simulation_data`, `scaled_raw` and
`modpoll-wot validate --kind data`. Modpoll `--export` snapshots are accepted
as simulation data. Verification report schema 3 replaces schema 2 and drops
`model.path`: Open Modbus Catalog keeps each baseline Thing Model at
`model.tm.json`, so the product ID and catalog commit identify it. Schema 2
had no consumers and is removed.

## Version 0.3.0a3

Version 0.3.0a3 removes the optional `modpoll:audit` plan and `AuditPlan`.
Baseline Thing Models are fully open, and a [full read](profile.md#verification-reports)
executes the whole `modpoll:acquisition` plan, so the audit list only repeated
acquisition members. Authors write `modpoll:acquisition` only. A TM or TD that
still declares `modpoll:audit` fails with `unsupported root project extension`.
Model and point fingerprints are unchanged, because the plan never contributed
to them. Open Modbus Catalog removed its audit plans before this release.

## Version 0.3.0a2

Version 0.3.0a2 replaces verification report schema 1 with
[schema 2](profile.md#verification-reports): `device` becomes `product`,
`environment.carrier` becomes `environment.chassis`, and `reportVersion` is 2.
Schema 1, released in 0.3.0a1, had no consumers and is removed. A TD or TM
with an empty title now fails with `/title: title cannot be empty`.

## Version 0.3.0a1

Version 0.3.0a1 adds [point and model fingerprints and verification reports](profile.md#point-and-model-fingerprints).
It removes `derive_audit_tm`, `AuditArtifact` and the `audit-tm-v1`
publication format, which existed only for restricted preview models. Point
tables now include fingerprints. The `modpoll:audit` plan is unchanged in this
version and removed in 0.3.0a3.

## Device metadata

Version 0.3.0a1 removes the device metadata schema 1, `validate-device` and
`modpoll_wot.metadata`, published in 0.2.0a3 and 0.2.0a4. Device metadata records
and their schema belong to [Open Modbus Catalog](https://github.com/top-maker/open-modbus-catalog).
No current consumer uses the removed API.

Version 0.2.0a4 adds optional audit references, removed in 0.3.0a3, and the
publication APIs removed in 0.3.0a1. Earlier packages
can run existing profile 0.2 documents that omit the extension. They reject
documents with the new audit extension. The shared package validates and
derives configuration without contacting any device.
