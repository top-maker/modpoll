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

Generation is reproducibly checked with `examples/generate-td.py --check` in
the candidate tool environment. Each product's generated.json links the exact
TM hash, target, tool version, instance parameters and TD artifact hashes.
These are generated views of a single maintained TM, not separate source models.

Hardware work remains: confirm the 5017UH range/data format and actual responses;
verify the candidate 6024 tables, addresses, normalization and output limits.
The current modsim runtime still does not load these TM/TD files.
