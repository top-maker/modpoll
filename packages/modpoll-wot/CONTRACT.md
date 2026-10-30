# Executable configuration contract 0.1 (preview)

This is Modpoll's supported WoT TM/TD 1.1 subset for replacing CSV configuration.
It is not a general WoT runtime. The Modbus binding document remains a draft:
https://w3c.github.io/wot-binding-templates/bindings/protocols/modbus/.
Its entity, address, quantity and byte/word-order vocabulary is reused. Ordered
acquisition groups, offsets, precise decoding and multipliers are project extensions.
They do not claim standard W3C acquisition or transformation semantics.

Use `modpoll-wot validate MODEL --profile [--unit-id N]` to validate a
model without opening a device connection. Schemas are bundled locally; the
loader does not dereference contexts or remote schema dependencies. The official
TD/TM schemas identify themselves as `1.1-12-March-2025` (Draft 7).

Modpoll accepts TM and TD inputs through the same `--config` option, selecting
the format from document content rather than a filename or URL suffix. A top-level `@type` string equal
to `tm:ThingModel`, or an array containing that value, selects TM validation.
Otherwise TD validation applies. Invalid input fails the selected schema without
retrying another kind. This fixed-alias subset does not resolve arbitrary
JSON-LD type aliases. The Python API's optional `kind` argument asserts the
expected kind; it does not override content detection.

| 1.x input | Contract 0.1 |
| --- | --- |
| device name | `title`, used verbatim as output device name |
| Unit ID | Optional root modv:unitID default per file; explicit CLI overrides it; fallback 1; range 1–254 |
| poll table | group `modv:entity`: Coil, DiscreteInput, InputRegister, HoldingRegister |
| poll start/count | group `modv:address` / `modv:quantity`, literal PDU addresses |
| poll endian | `modv:mostSignificantByte` and `modv:mostSignificantWord` booleans |
| ref effective name | property key and member `modpoll:property` |
| ref address | member `modpoll:offset`, relative to group start |
| ref `address:bit` | member `modpoll:bit`, 0–15, register bool only |
| ref dtype | member `modpoll:dataType` |
| ref rw | standard property `readOnly` / `writeOnly`; neither means rw |
| ref unit | standard property `unit` |
| ref scale | member `modpoll:multiplier`, multiplication, never inferred division |

The JSON root declares `modpoll:version: "0.1"` and `modpoll:acquisition`.
Context aliases must match the supported project and draft Modbus namespaces;
these are not arbitrary remotely resolved JSON-LD aliases. The project namespace
documents contract 0.1 at https://top-maker.github.io/modpoll/vocab/wot-modbus.
This is a project extension, not a W3C Modbus standard. Concrete TD Forms use `modbus+tcp` URLs. The Form's entity, operations,
unit/address/quantity and declared payload/byte order must match the group/member.
Explicit transport CLI options select the actual endpoint, allowing the same
configuration to be tested through a proxy or alternate transport. Concrete TD
Unit IDs must match `--unit-id`; unbound TMs can be instantiated with any supported ID.

Register member offsets count 16-bit registers. Bit-table member offsets count
eight-bit groups relative to poll start, preserving the old behavior; poll counts
still specify physical bits. A final partial bit group is clipped by the executor.
Bit tables support bool/bool8/bool16 and numeric/string payloads that fit complete
requested bytes. Numeric assembly preserves v1 bit reversal within each byte; word
order is ignored for bit-table numeric decoding as in v1. Register types are int/uint16/32/64, float16/32/64,
bool/bool8/bool16 and stringN. String lengths count bytes, including odd lengths;
spans must fit the declared block. A register bool with a bit selector is a scalar
boolean; bool groups are arrays with boolean items. Strings cannot be multiplied.
Float and fractional-multiplier outputs require a number property schema.

Groups preserve order, boundaries and holes. Reads are limited to 125 registers
or 2000 physical bits per request, within 0–65535. No coalescing takes place.
Each property must have exactly one mapping. Distinct property aliases at the same backing address/bit are retained and
decoded independently from one request.
Overlapping views at distinct starting offsets remain explicit, independent values.
Missing fields, unknown executable extension fields, invalid access, non-finite
values/multipliers, duplicate JSON keys and invalid type combinations fail the
whole file with source and field diagnostics. Inputs are bounded to 1 MiB and 64
nested containers. Invalid files do not yield partially configured devices.

DI/IR are read-only. The historical simulator CSV's rw flags for those tables are
corrected to readOnly in the fixtures; no unsupported write capability is promised.
The interpreter records access flags; raw MQTT write commands retain the 1.x raw
address behavior. This milestone does not add property-based writes or inverse
engineering-value transforms. Multipliers are retained as Decimal in the model
but adapted to the existing float execution semantics. Int64 without a multiplier
stays a Python integer. JSON/JavaScript consumers must still account for their own
numeric precision limits.

Inheritance, links, optional TM members, URI templates, root operation Forms,
actions/events, unsupported Form terms and non-nosec security schemes are rejected.
Model/TD schema validation does not prove that a stock WoT consumer will implement
this acquisition extension or its transforms. In particular, a direct Modbus Form
identifies raw device access; engineering-value interpretation requires the project
transform metadata. No HTTP endpoint or cache service is declared.

The profile 0.1 compatibility fixtures (`modsim-0.1.tm.json` and
`modsim-0.1.td.json`) live under this package's tests. They preserve the original
CSV mapping for compatibility checks; they are not the current user examples.
The canonical v2 example uses profile 0.2 in `examples/modsim.tm.json` and is
covered by the profile 0.2 tests. Runtime equivalence checks compare independently
known initial values, complete JSON snapshots, rendered tables, and the exact
four requests against modsim. Shared remote modsim state may have been written by
others, so remote checks compare successive read-only snapshots rather than
assuming fixed initial values.

The shared interpreter is independently versioned and published as
`modpoll-wot`. Application previews pin an exact registry version.
Its schemas are bundled for offline use; new profile semantics require an
explicit contract revision rather than silently changing contract 0.1.
