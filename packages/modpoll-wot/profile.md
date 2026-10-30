# Executable profile 0.2

This profile is published as `modpoll-wot==0.2.0a1` and used by the Modpoll
`2.0.0a2` preview. It replaces the unpublished `0.2-pilot` experiment. No
local-path dependency is introduced. Contract 0.1 semantics remain unchanged.

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
words for register tables and physical bits for bit tables in 0.2; 0.1 retains
its historical eight-bit-group convention. Mixed byte orders are per member.

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

From the repository (omit PYTHONPATH with an installed candidate wheel):

```sh
PYTHONPATH=packages/modpoll-wot uv run python -m modpoll_wot \
  export examples/modsim.tm.json --host 127.0.0.1 --port 5020 \
  --unit-id 7 -o /tmp/modsim-instance.td.json
PYTHONPATH=packages/modpoll-wot uv run python -m modpoll_wot \
  validate /tmp/modsim-instance.td.json --profile
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

`tools/test-wot-source.py` exports the candidate import path to child CLIs as
well as pytest. The Python matrix runs the registry-pin suite first, then this
source suite; pytest's parent-only pythonpath option cannot replace this step.

The distribution gate `tools/verify-wot-distribution.py` builds a disposable
consumer wheel with the candidate's exact registry pin and tests both installed
wheels from outside the repository, with no source package imports. It never
modifies the real consumer pin. Its report requires no skipped tests.

Install locked interop tools with `npm ci --prefix tools/wot-interop
--ignore-scripts --no-audit --no-fund`. Node is pinned in .tool-versions; lockfile
integrities fix transitive dependencies. CI uses an isolated modsim and checks
actual reads/writes, not just successful TD parsing.

## Promotion order

Contract 0.1 compatibility fixtures live under the package tests. The canonical
examples/modsim.tm.json is the four-block/37-property source; generated TDs are
artifacts. Tests cover
value/request equivalence, mixed orders, aliases, holes, UTF-8 byte capacities,
physical bit offsets, parameters and external read/write round trips.

Pass source and installed-wheel checks, publish the immutable shared package via
the guarded core workflow, verify registry installation, then independently update
consumer exact pins and CI. Project versions need not match. Until producer-first
publication completes, no consumer requires an unpublished version or local path.
The modsim TD runtime and platform lifecycle remain separate implementation tasks;
this contract does not claim those applications are implemented.
