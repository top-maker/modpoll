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
