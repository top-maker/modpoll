# ADAM example transport verification

Manual verification on 2026-10-29 used the shared `modpoll-wot 0.2.0a1` tool,
`@node-wot/core` and `@node-wot/binding-modbus` 0.9.2, and an independent
PyModbus 3.16.1 synthetic TCP server on a temporary loopback port. No physical
ADAM device was connected and no manufacturer address/range claim was verified.

- The server was initialized directly with known arrays, without reading a TM:
  input words at PDU address i contained 60000+i, holding words 10/11 contained
  123/456, DI 0/1 contained true/false, and coils 16/17 contained false/true.
- The project's TM and generated project TD compiled to identical block mappings.
  The application read all values correctly; FC4 remained one block of 8 words
  at PDU 1 for 5017UH and one block of 6 words at PDU 0 for 6024.
- The unchanged node-wot Consumer used generated external TDs, with no project
  extension parser or custom value conversion. All 8 properties of 5017UH and
  all 12 properties of 6024 matched independent known values. Unsigned input
  values above 32767 were included to detect signed-decoding mistakes.
- On the synthetic 6024 service only, node-wot wrote AO0_RAW=321 and DO0=true.
  An independent Python client read holding register 10 and coil 16 to confirm
  the written values. These values are test data, not legal physical AO ranges.
- Every vendor PDF's bytes still matched the hashes in its sources.json.

Generation is reproducibly checked with `tools/generate-td.py --check` in
the candidate tool environment. Each product's generated.json links the exact
TM hash, target, tool version, instance parameters and TD artifact hashes.
These are generated views of a single maintained TM, not separate source models.

Hardware work remains: confirm the 5017UH range/data format and actual responses;
verify the candidate 6024 tables, addresses, normalization and output limits.
At the time of this verification, the modsim runtime did not load these TM/TD files.
The current v2 runtime supports the native raw-I/O subset; see
[configuration](../docs/model-validation.md).

## Shared TD follow-up (2026-10-29)

The examples now generate one `*.generated.td.json` per TM, retaining
`modpoll:version` and `modpoll:acquisition`. Source Forms explicitly state
unsigned binary media parameters. Filenames no longer contain `raw`; analog
property identifiers and unscaled value semantics are unchanged.

The same synthetic server procedure was repeated with the project TD, without
using the node-wot export target. Both the project interpreter and unchanged
node-wot 0.9.2 read all 8/12 properties correctly, including unsigned words above
32767. node-wot wrote AO0_RAW=321 and DO0=true on the virtual 6024; independent
Python reads confirmed both writes. Project TM/TD block mappings were identical,
and FC4 block reads remained unchanged. The shared package's 41 tests passed,
including rejection of conflicting, duplicate and unknown media parameters.
The earlier separate-target verification above is historical; those separate TD
artifacts have been removed. No physical device was connected.


## Configured runtime codec validation (2026-10-29)

The v2 working tree now uses one property codec for initialization, scripts,
generators and protocol writes. Independent constant wire vectors cover integer
and IEEE types, four byte/word orders, UTF-8 capacity/padding, native and legacy
boolean layouts, inverse multipliers, bit masks and alias validation. TCP tests
exercise partial-register writes, rollback, write-only registers/coils and
independent device state. These tests are synthetic; no ADAM hardware was used.

A separate end-to-end run used modpoll `6b6f897` and its canonical
`examples/modsim.tm.json` (profile 0.2, four groups, 37 properties) against the
modified modsim server, with both applications using published
`modpoll-wot==0.2.0a1`. Explicit initial values included signed integers, uint64
and int64 values above 2**53 in magnitude, floats, strings, boolean arrays and
the model's four scaled integer mappings. The real modpoll CLI read all 37 values
exactly as expected over TCP. An independent PyModbus client then changed uint32,
float64 and coil values; a second modpoll read again matched all 37 expected
values. This validates the runtime mapping and wire interpretation, not hardware
specifications or physical-unit assumptions.
