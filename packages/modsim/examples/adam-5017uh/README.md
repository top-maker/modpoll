# ADAM-5017UH through ADAM-5000L/TCP

This is the first hardware-reference candidate for the planned TD-driven modsim v2.
The operator confirmed **slot 0** and that no other I/O modules are installed.
The selected per-channel ranges, current data format and actual response captures
are still unknown. The files do not claim completed hardware verification.

## Files

- [Raw TD](adam-5017uh-slot-0-raw.td.json): eight input words in one block.
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
The TD consequently uses FC4/start 1/count 8, with offsets 0–7. This is based on
that explicit packet, not the usual assumption that 40001 always means PDU 0.
Confirm it against this rack/firmware before treating the TD as authoritative.

`AI0_RAW` through `AI7_RAW` preserve uint16 wire words with no multiplier. They
retain the bit pattern even if the underlying measurement uses a signed or
normalized representation. `count` denotes a raw word; it does not mean volts,
milliamps, measured ADC resolution or a configured channel's engineering range.
Engineering-value properties will be added after the selected ranges and wire
format are known. In particular, do not infer a scaling denominator from ADC bits.

Forms point to `127.0.0.1:5020`, a local simulator endpoint. Modpoll selects the
real host/port using its CLI. The Unit ID must agree with the TD.

Validate using the published shared interpreter:

    python -m modpoll_wot examples/adam-5017uh/adam-5017uh-slot-0-raw.td.json

For a read-only physical comparison from the modpoll development environment:

```sh
modpoll --once --tcp "$ADAM_HOST" --tcp-port 502 \
  --config /path/to/modsim/examples/adam-5017uh/adam-5017uh-slot-0-raw.td.json
```

Record raw words and compare against the vendor utility before assigning physical
units. This fixture does not change range, calibration or module settings.
The current modsim 1.x CLI has no `--config` option; this TD is prepared for the
shared configuration contract and modpoll, ahead of modsim v2 implementation.
