# ADAM-5017UH through ADAM-5000L/TCP

This is the first hardware-reference candidate for the planned TM-driven modsim v2.
The operator confirmed **slot 0** and that no other I/O modules are installed.
The selected per-channel ranges, current data format and actual response captures
are still unknown. The files do not claim completed hardware verification.

## Files

- [Source TM](adam-5017uh-slot-0.tm.json): the maintained mapping, eight raw input properties in one block.
- [Generated project TD](adam-5017uh-slot-0.generated.td.json): loopback instance, retaining acquisition policy.
- [Generation manifest](generated.json): source/artifact hashes, tool version and example instance parameters. Never edit generated TDs by hand.
- [Rack/protocol manual, edition 1](adam-5000-tcp-user-manual-ed1.pdf): slot mapping
  in section 3.5, printed page 26 (PDF page 34); explicit request/response in
  section 6.3.1, printed page 61 (PDF page 69).
- [I/O module manual, edition 4](adam-5000-io-user-manual-ed4.pdf): section 1.2.5,
  printed pages 14–16 (PDF pages 22–24), covers 5017UH specifications and ranges.
- [Sources and SHA-256](sources.json): original vendor URLs and unchanged PDFs.
  Vendor documents retain their original copyright and are not MIT-licensed.

## Address and value assumptions

The rack manual's Figure 6.1 sends Unit ID 1, FC4, PDU start **1**, count 2 for
slot-0 channel words 40001/40002. Figure 3.10 assigns eight words to slot 0.
The TM consequently uses FC4/start 1/count 8. Each property Form declares its
actual PDU address (1–8); acquisition only lists the block and its members. This is based on
that explicit packet, not the usual assumption that 40001 always means PDU 0.
Confirm it against this rack/firmware before treating the TD as authoritative.

`AI0_RAW` through `AI7_RAW` preserve uint16 wire words with no multiplier. They
retain the bit pattern even if the underlying measurement uses a signed or
normalized representation. `count` denotes a raw word; it does not mean volts,
milliamps, measured ADC resolution or a configured channel's engineering range.
Engineering-value properties will be added after the selected ranges and wire
format are known. In particular, do not infer a scaling denominator from ADC bits.

The source TM has no deployed host, port or Unit ID. Generated TDs demonstrate
`127.0.0.1:5020`, Unit ID 1; this is a loopback example, not the physical rack.
The generated TD retains acquisition metadata and explicitly describes unsigned
binary values in its Forms. Generic bindings such as node-wot ignore
`modpoll:acquisition`; they use the same property Forms without a separate TD.
No transformation or custom decoding is required for these raw words.

Use the profile 0.2 candidate tool environment described in [the examples guide](../README.md):

```sh
mise exec -- /tmp/modsim-wot-tools/bin/python examples/generate-td.py --check
```

A candidate-enabled modpoll can use the TM as its configuration source:

```sh
modpoll --once --tcp "$ADAM_HOST" --tcp-port 502 --unit-id 1 \
  --config /path/to/modsim/examples/adam-5017uh/adam-5017uh-slot-0.tm.json
```

For an external Consumer, generate a separate instance with its actual endpoint:

```sh
mise exec -- /tmp/modsim-wot-tools/bin/python -m modpoll_wot \
  --config examples/adam-5017uh/adam-5017uh-slot-0.tm.json \
  --host "$ADAM_HOST" --port 502 --unit-id 1 --target project \
  --output /tmp/adam-5017uh-instance.td.json
```

Record raw words and compare against the vendor utility before assigning physical
units. This fixture does not change range, calibration or module settings.
The `v2` development branch has a candidate native raw-I/O `--config` path.
See [model validation](../../docs/model-validation.md) for its isolated SDK environment
and supported subset. The released modsim 1.x CLI does not load these models.

Synthetic read/write compatibility is recorded in [the verification report](../verification.md); it does not establish hardware correctness.
