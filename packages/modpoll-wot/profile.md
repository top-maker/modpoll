# Executable profile 0.2

The published Modpoll `2.0.0a2` preview uses `modpoll-wot==0.2.0a1`.
Shared interpreter `0.2.0a3` and current development source execute only profile
0.2; profile 0.1 must be migrated before use. Older immutable application and
interpreter releases keep their original behavior. Package, profile and metadata
schema versions are independent; no local-path dependency is introduced.

## Source and instances

Product TM is the maintained source; TD is a generated instance artifact and a
supported input. A single `--config` accepts either format based on content,
independently of filename/URL. Invalid input fails its selected schema without
retrying another kind. Fixed vocabulary aliases are required.

Property DataSchemas hold standard types, access flags, units and constraints.
Forms supply literal PDU addresses, quantities, raw `modv:type`, entities and
byte/word order. Quantity defaults to 1; byte/word order flags default to true.
DataSchema `integer` does not imply a particular raw width. A combined read/write
Form or disjoint operation-specific Forms are accepted when they describe the
same mapping. Duplicate operations or disagreeing mappings fail.

Acquisition only holds explicit physical blocks and property names:

```json
{
  "modv:entity": "HoldingRegister",
  "modv:address": 40000,
  "modv:quantity": 8,
  "modpoll:members": ["counter", "signed", "measurement"]
}
```

This group object is a project extension, even though its fields reuse Modbus
vocabulary. Group order, holes and boundaries are preserved without coalescing
or splitting. Every property belongs to one group; explicit aliases may share
addresses. Decoder metadata and offsets are derived from Forms. Offsets count
words for register tables and physical bits for bit tables. Mixed byte orders
are per member.

TM Forms can omit href. Standard TM placeholders are also supported. CLI binds
host/port/Unit ID; TCP port defaults to 502 and Unit ID to 1 (range 1–254).
Reserved placeholder names are HOST, PORT, UNIT_ID and AUTHORITY (host plus port,
including IPv6 brackets). Named instance flags take precedence over `--param`
values for reserved bindings. Other parameters use `--param NAME=JSON`. A whole
value placeholder preserves its JSON type. Missing, malformed or unused bindings
fail; arbitrary JSON patches and code execution are not supported.

TD declarations are validated before overrides. Standard Form modv:unitID,
when present, must agree with the URI and all other Forms and is updated on
explicit rebinding. Source TM identity is copied as defined by TM derivation;
use an id placeholder and a persistent instance UUID parameter for multiple
devices. The platform owns instance identity; the interpreter does not infer a
physical identity from IP/port or silently create a random ID. Without explicit flags its
endpoint and Unit ID are authoritative. Explicit overrides update all Forms in
the effective TD and cannot hide inconsistent source metadata. Listening wildcard
addresses cannot be exported. Plain IPv6 literals are canonicalized; scoped
IPv6 addresses are currently rejected. Simulators must distinguish listening interfaces
from advertised endpoints. Unbound TM execution supports explicit serial/UDP
connections; concrete TCP TD export requires a TCP endpoint and never invents
RTU/UDP URLs. A bound TCP instance cannot silently become serial/UDP.

## Necessary extensions

| Form field | Meaning |
| --- | --- |
| `modpoll:multiplier` | Finite number/decimal string; engineering = raw × multiplier, including zero/negative values |
| `modpoll:bit` | Bit 0–15 of raw xsd:unsignedShort; boolean property |
| `modpoll:codec` | float16 or historical register bool/bool8/bool16 array codec, with raw xsd:hexBinary |
| `modpoll:byteLength` | Exact UTF-8 capacity when different from the full register span; bytes, not characters |
| `modpoll:bitPacking` | legacy-msb for deliberately packed numeric/string bit-table payloads |

Native Coil/DiscreteInput booleans/boolean arrays use xsd:boolean and physical
counts without an extension. Register boolean scalars use xsd:boolean, quantity 1.
Register strings apply byte/word order to the padded register span before taking
the declared byte capacity. Legacy register boolean arrays retain their historical
byte interpretation and widths. Explicit packed bit codecs retain legacy behavior,
including ignoring word order; they are not portable scalar Modbus mappings.

Property schemas are retained in immutable `Model.properties_json` for consumers.
This does not invent manufacturer ranges, generate simulator state, enforce
business ranges on live samples or add inverse engineering-value writes. No
scheduler, cache or waveform is implied. Unsupported pollingTime/timeout execution,
inheritance, optional members, imports, root operations and non-nosec security
fail explicitly. These are defined subset limits, not silent fallback behavior.

## API and CLI

```python
from modpoll_wot import load_model, instantiate, export_td
model = load_model("meter.tm.json", host="127.0.0.1", port=5020, unit_id=7)
model, effective = instantiate(document, host="127.0.0.1", unit_id=7)
td = export_td(document, host="127.0.0.1", target="project")
```

No input is mutated, no connection opened, and execution needs no temporary TD.
Without an endpoint instantiate's second result is a partial description; only
export_td promises a complete TD. Exports pass bundled TD 1.1, the pinned official
Modbus schema and project cross-field checks offline. See schemas/SOURCES.md.

From a checkout of this repository (use `modpoll-wot` directly with an installed wheel):

```sh
uv run modpoll-wot export tests/fixtures/modsim.tm.json --host 127.0.0.1 \
  --port 5020 --unit-id 7 -o /tmp/modsim-instance.td.json
uv run modpoll-wot validate /tmp/modsim-instance.td.json --profile
```

Existing output files are never overwritten. These subcommands require shared package 0.2.0a2 or newer. The shared package supplies models/metadata, not a
Modbus client/server, scheduler or MQTT service.

## Shared TD and binary media parameters

Project TDs may retain acquisition metadata when consumed by third-party tools.
node-wot 0.9.2 preserves unknown project fields without executing them; removing
those fields is not a prerequisite for consumption. Prefer one generated TD per
TM, shared by project tools and external Consumers.

Native scalar Forms may specify octet-stream `length`, `signed` and `byteSeq`
parameters. The interpreter checks them against the raw type, quantity and
byte/word order and rejects conflicts, duplicates and unknown parameters.
Parameterized custom codecs, arrays and transformed values are not supported.
The ADAM examples in modsim use this shared representation; filenames mark
outputs as `*.generated.td.json` and only TMs are maintained by hand.

## Actual external Consumer

The `node-wot-0.9.2` export target is verified with pinned @node-wot/core and
@node-wot/binding-modbus 0.9.2. It emits standard TD Forms, removes acquisition
metadata and supplies octet-stream length/signed/byteSeq media parameters. The
external Consumer contains no project decoding or value conversion. Separate
operation Forms use FC16 for register writes, avoiding the client's FC6 byte
swapping. Word order has no effect on a single register.

Supported targets include 16/32-bit integers, 32/64-bit floats and scalar booleans.
Four read byte/word orders are verified. Multiword mixed-order writes are rejected
because this client cannot encode them correctly. Strings, arrays, 64-bit integers,
custom codecs, bit extraction and multipliers fail by property name rather than
being stripped or misrepresented. Project TD output retains those semantics.
No HTTP/cache endpoint is declared without an actual service.

CI in this repository tests the source on the supported Python range, builds
the wheel and sdist, checks the installed wheel from outside the source tree,
and runs the Modpoll and Modsim test suites against the built wheel. The
node-wot interoperability gate remains in Modpoll and runs against its pinned
release.

## Promotion order

The canonical tests/fixtures/modsim.tm.json is the four-block/37-property source; generated TDs are
artifacts. Tests cover
value/request equivalence, mixed orders, aliases, holes, UTF-8 byte capacities,
physical bit offsets, parameters and external read/write round trips.

Pass source and installed-wheel checks, publish the immutable shared package via
this repository's release workflow, verify registry installation, then independently update
consumer exact pins and CI. Project versions need not match. Until producer-first
publication completes, no consumer requires an unpublished version or local path.
The modsim TD runtime and platform lifecycle remain separate implementation tasks;
this contract does not claim those applications are implemented.


### Optional audit plan

A project TM or TD can declare `modpoll:audit` with an `identity` array, a
`status` array, or both. Each supplied array contains one or more property names
in reporting order. A name may occur only once in the plan and must resolve to a
property with a read Form. Validation checks these references before any device
I/O. The property Forms remain the authority for addresses and codecs.

Project TD export retains the plan. The explicitly selected node-wot export
omits project extensions. Audit references describe a local client operation
and do not add WoT actions to a device.

### Point tables

`project_point_table(tm_bytes)` produces rows in acquisition member order.
Addresses are zero-based and quantities count the registers or bits read by
the individual Form. Read function codes are null for write-only points.
A writable flag records access without inferring a write function code.
Multipliers are decimal strings when present. Each readable row carries its
point fingerprint; write-only rows carry null.

## Point and model fingerprints

A point fingerprint identifies how one readable property is acquired and
decoded, independently of the file that contains it. A model fingerprint
identifies the set of readable point mappings of a whole model. Verification
statistics are keyed by the model fingerprint: titles, descriptions, units,
property names and member order do not change it, so a custom TM whose read
mappings are unchanged shares the fingerprint and statistics of its upstream
TM, while any change to a read mapping, or adding or
removing a readable point, starts a new one.

`point_fingerprints(model)` accepts a TM or TD, as a parsed document or exact
bytes, and returns `{property: fingerprint}` for every readable property.
`model_fingerprint(model)` returns the model fingerprint.
`modpoll-wot fingerprint FILE` prints both as JSON
(`{"model": ..., "points": {...}}`). The model is
instantiated without instance arguments, then each property's read Form is
reduced to this canonical object:

| Key | Value |
| --- | --- |
| `type` | Property DataSchema type |
| `modv:entity`, `modv:address`, `modv:quantity`, `modv:type` | From the Form; quantity is filled with its default |
| `modv:mostSignificantByte`, `modv:mostSignificantWord` | From the Form, defaulting to true |
| `modpoll:codec`, `modpoll:bit`, `modpoll:bitPacking` | Only when present |
| `modpoll:multiplier` | Only when present, as a plain decimal string without exponent or trailing zeros (`0.1`, `100`) |
| `modpoll:byteLength` | Always for `xsd:string`, filled with the full span capacity by default; never otherwise |

The fingerprint is `pf1:` followed by the lowercase SHA-256 hex digest of the
object serialized as UTF-8 JSON with sorted keys, no whitespace and non-ASCII
characters unescaped. Property names, titles, descriptions, units, ranges,
write Forms, endpoints and Unit IDs do not contribute. Flags that a type cannot
use, such as word order for a single register, are kept as written: equivalent
spellings may split statistics but never merge different mappings.
The model fingerprint is `mf1:` followed by the SHA-256 hex digest of the
sorted, deduplicated point fingerprints serialized as a JSON array without
whitespace. Aliases with identical mappings count once; write-only properties
do not contribute.
[tests/fixtures/modsim.fingerprints.json](tests/fixtures/modsim.fingerprints.json)
pins the canonical strings, point fingerprints and model fingerprint of the
37-property fixture for other implementations. Changing either canonical form
requires a new prefix.

## Verification reports

A verification report records one reading of a Thing Model on a physical device. Its schema is
[schemas/verification-report-2.json](modpoll_wot/schemas/verification-report-2.json)
(JSON Schema 2020-12). A report carries:

- `product`: the catalog product ID `<manufacturer>/<model-number>`.
- `model`: the SHA-256 of the exact TM bytes, its model fingerprint and its
  source. Catalog models add
  the 40-character catalog commit and package-relative `models/*.tm.json`
  path. Custom TMs add an opaque version reference. Local models add
  neither.
- `tool`: the reporting tool's name and version, and the modpoll-wot version.
- `transport` (`tcp` or `rtu`) and the reading `date`.
- Optional `environment`: chassis product ID, firmware and a short
  configuration note, such as an input range code.
- `points`: per property, its fingerprint, the read result (`ok`,
  `exception` with its exception code, `no-response` or `not-tested`) and
  the user's judgment of the value (`confirmed`, `rejected` or `unchecked`).
  Only a successful read can be judged.

A report is a full read when its points cover every readable property of the
model and every read is `ok`, so that executing the whole
`modpoll:acquisition` plan raised no error. Receiving services derive this
from the stored per-point results.

The schema rejects every other field. Endpoints, Unit IDs, serial numbers and
read values therefore cannot be sent. Configuration notes are free text, so
the reporting tool shows the report for review before upload. Review
markers and account data belong to the receiving service, not the report.

`validate_report(report, model=tm_bytes)` and
`modpoll-wot validate-report REPORT [--model TM]` check the schema and unique
properties. With the model, they also check its hash and model fingerprint, and that
every point names a readable property with a matching fingerprint.
