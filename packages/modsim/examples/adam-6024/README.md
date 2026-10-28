# ADAM-6024 core I/O candidate

Second, specification-based model for the planned simulator: six AI, two AO,
two DI and two DO channels. This fixture has not been checked against hardware.

## Files

- [Raw TD](adam-6024-raw.td.json): four groups and ten properties representing
  twelve physical channels; each digital property is a two-element boolean array.
- [ADAM-6000 manual, edition 12](adam-6000-user-manual-ed12.pdf): specifications
  in section 4.6, printed pages 28–29; ADAM-6024 mapping in appendix B.2,
  printed pages 203–204 (PDF pages 213–214).
- [Official Modbus/LabVIEW guide](adam-modbus-labview-guide.pdf): page 7 shows
  an ADAM-6024 DO write with starting address **16**.
- [Sources and SHA-256](sources.json): vendor URLs and unchanged PDF hashes.
  Vendor documents retain their copyright and are not MIT-licensed.

## Candidate mapping

| I/O | Manual reference | Selected table | TD PDU start | Count |
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

Forms use local simulator endpoint `127.0.0.1:5020`, Unit ID 1. Modpoll selects its
actual endpoint by CLI. DI/DO use arrays to retain block reads within profile 0.1;
that profile does not currently provide scalar per-coil bit-offset properties.

```sh
python -m modpoll_wot examples/adam-6024/adam-6024-raw.td.json
```

AO/DO are declared writable for future simulated-device tests. This draft is not
a command to write to physical outputs. Confirm mapping and permitted values
before hardware output tests. Current modsim 1.x cannot load TD files yet.
