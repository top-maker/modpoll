# Siemens 5SL60...MC measurement subset

This model covers 15 read-only measurements from Siemens' original FW-V7.3
Thing Model: temperature, current, voltage, frequency, power, power factor and
energy. It is a partial model, not a complete device or protection simulation.
Commands, settings, status, identification and other source properties are not
included. The source TM and the older system manual are in [specs](specs/);
the manual's section 6.5.4.6, printed page 89 (PDF page 91), describes these
5SL6 COM measurements. See [sources.json](specs/sources.json) for the PDF's
origin and copyright. The original TM declares an Apache-2.0 license.

The source uses `zeroBasedAddressing: false`; this model interprets that as
one-based and subtracts one to obtain literal PDU addresses (for example,
source temperature register 3072 becomes address 3071). The 2023 manual lists
register 3072 but does not independently establish that interpretation here.
The model assumes big-endian bytes and words for FP32/FP64; neither that order
nor the address translation has been verified on a real device. The manual
also describes an unavailable value as `0xFFFFFFFF`; no special handling of
non-finite readings is modeled. Confirm addressing, byte order, firmware and
invalid-value handling with the target device before relying on readings.
The single contiguous acquisition block covers PDU addresses 3071–3108.
Observe operations and the source polling interval are not represented.

Validate with the repository's pinned `modpoll-wot==0.2.0a2`:

```sh
uv run python -m modpoll_wot validate \
  contrib/siemens/5sl60-x-mc/5sl60-x-mc.tm.json --kind tm --profile
uv run python -m modpoll_wot export \
  contrib/siemens/5sl60-x-mc/5sl60-x-mc.tm.json \
  --host 127.0.0.1 --port 5020 --unit-id 1 \
  -o /tmp/5sl60-x-mc-instance.td.json
uv run python -m modpoll_wot validate /tmp/5sl60-x-mc-instance.td.json \
  --kind td --profile
```

The endpoint is an example for a simulator. Profile validation checks structure
and the executable contract; it does not validate device behavior or wire data.
