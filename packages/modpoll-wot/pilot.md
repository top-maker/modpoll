# Standards-first TM/TD pilot

This is an isolated, unpublished experiment (`modpoll:version: "0.2-pilot"`),
not a new supported contract. The normal Modpoll `--config` loader continues to
accept contract 0.1 and rejects this pilot format. No application dependency pin
or default execution path changes. The implementation lives in `modpoll_wot.pilot`.

## Source and instance

Maintain a TM as the source. Each property has exactly one Modbus Form with
`modv:entity`, `modv:address`, `modv:type`, optional `modv:quantity` (default 1),
and optional byte/word-order flags (both default true). The TM Form omits `href`.
Property schemas retain standard types, access flags and other metadata.

Acquisition contains ordered block boundaries and property names only:

```json
{
  "modv:entity": "HoldingRegister",
  "modv:address": 40000,
  "modv:quantity": 8,
  "modpoll:members": ["counter", "signed", "measurement"]
}
```

The block object is a **project extension**. Reusing Modbus vocabulary within it
does not make grouped acquisition a W3C-defined operation. Offsets and codec types
are derived from property Forms; source/exported files do not repeat them as
`modpoll:offset` or `modpoll:dataType`. Explicit blocks, holes and order are retained.

The fixture `tests/fixtures/numeric-pilot.tm.json` is a synthetic test device,
not a manufacturer register map. It contains unsigned 16-bit, signed 16-bit and
32-bit floating-point values in one block with holes.

From the repository root, using the mise-managed project environment:

```sh
PYTHONPATH=packages/modpoll-wot mise exec -- poetry run python -m modpoll_wot.pilot \
  --config packages/modpoll-wot/tests/fixtures/numeric-pilot.tm.json \
  --host 127.0.0.1 --port 5020 --unit-id 7 --output /tmp/numeric-pilot.td.json

PYTHONPATH=packages/modpoll-wot mise exec -- poetry run python -m modpoll_wot.pilot \
  --config /tmp/numeric-pilot.td.json --output /tmp/numeric-pilot-roundtrip.json
```

The CLI uses the same `--config` for TM and TD, recognizing document content.
Outputs are created exclusively: an existing output is not overwritten. TD input
uses its concrete endpoint and rejects instance overrides in this experiment.
Wildcard listening addresses are rejected as advertised endpoints. This module
does not implement server listening, discovery or an HTTP/cache service.

The API `compile_model(document, host=..., port=..., unit_id=...)` returns an
execution Model and a validated concrete TD. It does not mutate the source or
contact a device. It binds TCP Forms, removes only the `tm:ThingModel` type and
adds a nosec declaration when absent. TD export is deterministic and retains
property metadata, custom application types and acquisition groups.

## Scope and limitations

- Numeric scalars in InputRegister/HoldingRegister: exact 16/32/64-bit integer
  and 32/64-bit floating-point types. Quantity must match the selected type.
- Fixed vocabulary aliases, one Form per property, one TCP endpoint and Unit ID.
- No transforms, bit tables, bit extraction, strings, root Modbus defaults,
  placeholders, inheritance or alternate Form selection. Unsupported Form terms
  fail rather than being removed during export.
- Byte/word order must be uniform within a block. The compatibility adapter uses
  the existing 0.1 execution checks internally, without exposing its duplicate
  codec fields in the exported TD. Mixed orders require changes to the internal
  member representation before promotion; blocks must not be split implicitly.
- Export passes the bundled standard TD 1.1 schema and project cross-field checks.
  This is not certification against every Modbus draft revision or an assertion
  of compatibility with node-wot. Independent external-client testing is pending.
- Constraints are retained; this experiment does not generate simulator values
  from constraints or add constraint enforcement to live polling.

## Verification and promotion gate

Unit checks cover numeric widths, all four uniform byte orders, nonmutation,
deterministic TM-to-TD-to-model equivalence, explicit block order, ambiguous
Forms, transforms, span/type mismatches, URI conflicts and endpoint validation.
A local modsim wire test independently encodes `42`, `-123`, `12.5` and hole words.
Both TM execution and reimported TD execute exactly one FC3 read of 8 registers
at address 40000 / Unit ID 7 and decode the same three values.

Before promotion: implement per-member endian handling, settle remaining legacy
codecs/transforms and parameter precedence, verify a pinned external Modbus WoT
client with real reads, and establish a versioned public contract/schema. Then
publish the shared package and independently update each consumer's exact pin.
The pilot does not initiate that migration or release.

References: [TD 1.1 TM derivation](https://www.w3.org/TR/wot-thing-description11/#thing-model),
[Modbus binding draft](https://w3c.github.io/wot-binding-templates/bindings/protocols/modbus/).
