# Synthetic verification evidence

On 2026-10-29, the ADAM TM/TD mappings were exercised against an independently
initialized PyModbus 3.16.1 TCP server using `modpoll-wot==0.2.0a1` and an
unchanged node-wot 0.9.2 consumer. No physical ADAM device was connected.

- All eight ADAM-5017UH and twelve ADAM-6024 properties matched known input
  values, including unsigned words above 32767. The FC4 reads retained their
  expected block boundaries.
- On the synthetic ADAM-6024 server, node-wot wrote AO0 and DO0; an independent
  Python client confirmed the corresponding holding register and coil values.
- Generated TDs are derived from their TM sources by `tools/generate-td.py`.
  Each product's `generated.json` records the source and artifact hashes,
  interpreter version and instance parameters.
- A separate synthetic end-to-end run with modpoll commit `6b6f897` read 37
  properties from modsim before and after independent register and coil writes.

These checks establish software interoperability for the tested vectors. They
do not establish physical device mappings or electrical ranges. The 5017UH
range/data format and 6024 address, scaling and output limits still need hardware
verification; see the product READMEs in [contrib](../contrib/README.md).
