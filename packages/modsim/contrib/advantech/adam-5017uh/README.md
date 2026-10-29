# ADAM-5017UH

Manual-derived model of the complete eight-channel analog input module.
`AI0_RAW` through `AI7_RAW` expose all eight channels as unscaled uint16 words.
The model is independent of a particular installed module or slot assignment.
Range settings, wire data format and physical responses remain unverified.

## Files

- [Source TM](adam-5017uh.tm.json): all eight input channels and one acquisition block.
- [Declarative scenario](simulation/adam-5017uh.sim.json): synthetic sine values for all eight analog input channels.
- [Scripted scenario](simulation/adam-5017uh-scripted-analog-input.sim.json) and [behavior](simulation/adam-5017uh-behavior.py): synthetic
  counts for all eight analog input channels, enabled with `--allow-scripts`.
- [Reference materials](specs/) and [source records](specs/sources.json): original vendor URLs, retrieval dates and PDF hashes.
  Vendor manuals retain their original copyright; they are not MIT-licensed.
  The model and example behaviors use the repository MIT license.

Reference PDFs and their provenance are kept together in `specs/`. Generated
TDs are created on demand. The reference manuals are:

- [ADAM-5000/TCP manual, edition 1](specs/adam-5000-tcp-user-manual-ed1.pdf):
  section 3.5, printed page 26 (PDF page 34), and section 6.3.1,
  printed page 61 (PDF page 69).
- [ADAM-5000 I/O manual, edition 4](specs/adam-5000-io-user-manual-ed4.pdf):
  section 1.2.5, printed pages 14–16 (PDF pages 22–24), covers ADAM-5017UH
  specifications and ranges.

## Mapping and scope

The reference mapping uses InputRegister / FC4, PDU addresses **1–8**, with a
single start-1/count-8 acquisition block. The rack manual's Figure 6.1 shows
FC4/start 1/count 2 for slot-0 channel words 40001/40002; Figure 3.10 assigns
eight words to that slot. This is the address basis for the module model,
not a restriction to an operator's slot-0 installation. A different rack or slot
may require different addresses; confirm the mapping for the target installation.
The TM describes one ADAM-5017UH module, not the other slots of a rack.

The unsigned representation preserves all 16 wire bits. `count` is a raw word,
not volts, milliamps, ADC resolution or a configured engineering range. No
physical conversion is assumed. Check channel ranges and wire format against
the vendor utility before assigning physical units. Range configuration,
calibration and rack management are outside this raw-input model.

## Use

From the repository root, start the complete module with synthetic input:

```sh
poetry run modsim --config contrib/advantech/adam-5017uh/adam-5017uh.tm.json \
  --unit-id 1 --port 5020 \
  --scenario contrib/advantech/adam-5017uh/simulation/adam-5017uh.sim.json
```

The source TM has no deployed host, port or Unit ID. To export a TD for an
external consumer using the project's pinned `modpoll-wot` dependency:

```sh
poetry run python -m modpoll_wot \
  --config contrib/advantech/adam-5017uh/adam-5017uh.tm.json \
  --host 127.0.0.1 --port 5020 --unit-id 1 --target project \
  --output /tmp/adam-5017uh-instance.td.json
```

For a physical device, substitute its verified endpoint and mapping. The
loopback endpoint above is a simulator example. See [model validation](../../../docs/model-validation.md)
for the supported profile 0.2 subset. modsim 1.x does not load these models.
Synthetic interoperability checks do not establish hardware correctness.
