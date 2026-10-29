# ADAM-6024 core I/O candidate

Second, specification-based model for the planned simulator: six AI, two AO,
two DI and two DO channels. This fixture has not been checked against hardware.

## Files

- [Source TM](adam-6024-raw.tm.json): the maintained mapping, four groups and twelve native per-channel properties.
- [Generated project TD](adam-6024-raw.td.json): loopback instance, including project acquisition policy.
- [Generated node-wot TD](adam-6024-raw.node-wot.td.json): standard Forms without project acquisition fields.
- [Generation manifest](generated.json): source/artifact hashes, tool version and instance parameters. Never hand-edit generated TDs.
- [ADAM-6000 manual, edition 12](adam-6000-user-manual-ed12.pdf): specifications
  in section 4.6, printed pages 28–29; ADAM-6024 mapping in appendix B.2,
  printed pages 203–204 (PDF pages 213–214).
- [Official Modbus/LabVIEW guide](adam-modbus-labview-guide.pdf): page 7 shows
  an ADAM-6024 DO write with starting address **16**.
- [Sources and SHA-256](sources.json): vendor URLs and unchanged PDF hashes.
  Vendor documents retain their copyright and are not MIT-licensed.

## Candidate mapping

| I/O | Manual reference | Selected table | PDU start | Count |
| --- | --- | --- | --- | --- |
| AI0–5 | 40001–40006 | InputRegister / FC4 | 0 | 6 words |
| AO0–1 | 40011–40012 | HoldingRegister / FC3 | 10 | 2 words |
| DI0–1 | 00001–00002 | DiscreteInput / FC2 | 0 | 2 bits |
| DO0–1 | 00017–00018 | Coil / FC1 | 16 | 2 bits |

DO start 16 is corroborated by the vendor's LabVIEW example. Other selected
starts and read tables are candidates derived from the reference map and protocol
conventions; verify them for the selected firmware. Some generic manual examples
use a different apparent address convention. Do not transfer the rack's explicit
start-1 packet to this product or silently call this draft hardware-validated.

Analog properties expose unscaled uint16 words. Their 0–65535 schema bounds are
transport-type bounds, not a verified legal AO range. Physical voltage/current
conversion, range codes and DAC quantization remain to be confirmed; 12-bit AO
hardware does not by itself establish the Modbus word normalization. No multiplier
or physical unit has been guessed. Range configuration, status, historical values,
watchdog, calibration and GCL/P2P behavior are outside this core I/O draft.

The source TM has no deployed endpoint. Its Forms contain the actual table,
address, quantity and raw type; acquisition only states the four block spans and
member names. DI0/DI1 and DO0/DO1 are scalar booleans at physical bit addresses
0/1 and 16/17. They replace the old two-element DI/DO properties so ordinary
bindings can address every channel, while the project's two-bit block reads are
preserved. There are now twelve properties for twelve channels.

Generated instances use loopback `127.0.0.1:5020`, Unit ID 1. The project TD is an
executable profile 0.2 instance; the node-wot 0.9.2 target contains standard
Forms/media parameters and no acquisition extension. External bindings ignore
project grouping and may issue individual property reads. No HTTP cache or
background acquisition service is implied.

See [the tool setup and generation guide](../README.md). To validate generation:

```sh
mise exec -- /tmp/modsim-wot-tools/bin/python examples/generate-td.py --check
```

To export a real endpoint for an external Consumer:

```sh
mise exec -- /tmp/modsim-wot-tools/bin/python -m modpoll_wot \
  --config examples/adam-6024/adam-6024-raw.tm.json \
  --host "$ADAM_HOST" --port 502 --unit-id 1 --target node-wot-0.9.2 \
  --output /tmp/adam-6024-instance.td.json
```

AO/DO are declared writable for future simulated-device tests. This draft is not
a command to write to physical outputs. Confirm mapping and permitted values
before hardware output tests. Current modsim 1.x cannot load TD files yet.

Synthetic read/write compatibility is recorded in [the verification report](../verification.md); it does not establish hardware correctness.
