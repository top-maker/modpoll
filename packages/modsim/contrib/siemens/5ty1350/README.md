# Siemens 5ty1350 read-only numeric subset

[5ty1350.tm.json](5ty1350.tm.json) contains 24 of 170 source properties. It is a partial model derived from the [original Siemens TM](specs/Siemens_5TY1350_FW-V7.3.tm.jsonld) (FW-V7.3, Apache-2.0). Of the 146 excluded properties, 100 are writable or write-only, 40 have non-numeric schemas, and 6 have a raw type width that differs from the register quantity. Categories are counted in that order and are mutually exclusive. No device-specific PDF is currently included in specs; mappings are derived from the vendor TM only.

Only read-only numeric fields whose source type and register quantity match a supported profile 0.2 scalar are included. Writable properties, commands, binary data, strings and width mismatches are excluded. Each acquisition reads a single property; no gaps are read. Observation and vendor polling intervals are not represented.

The source declares `zeroBasedAddressing: false`; the model interprets the source address as one-based and subtracts one for a literal PDU address. Big-endian byte and word order is assumed. Neither assumption nor the field meaning has been independently verified for this firmware or real hardware. Invalid-value encodings are not modeled. Verify mappings, byte order, and firmware against the device before relying on results.

Validate and export with `modpoll-wot==0.2.0a2`:

```sh
poetry run python -m modpoll_wot validate contrib/siemens/5ty1350/5ty1350.tm.json --kind tm --profile
poetry run python -m modpoll_wot export contrib/siemens/5ty1350/5ty1350.tm.json --host 127.0.0.1 --port 15020 --unit-id 1 -o /tmp/5ty1350.td.json
poetry run python -m modpoll_wot validate /tmp/5ty1350.td.json --kind td --profile
```

The loopback endpoint is a simulation example. Profile validation does not verify device behavior or wire data.
