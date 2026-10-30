# Siemens 7kn12100mc00 read-only numeric subset

[7kn12100mc00.tm.json](7kn12100mc00.tm.json) contains 16 of 568 source properties. It is a partial model derived from the [original Siemens TM](specs/Siemens_7KN12100MC00_FW-V7.3.tm.jsonld) (FW-V7.3, Apache-2.0). Of the 552 excluded properties, 175 are writable or write-only, 374 have non-numeric schemas, and 3 have a raw type width that differs from the register quantity. Categories are counted in that order and are mutually exclusive. No device-specific PDF is currently included in specs; mappings are derived from the vendor TM only.

Only read-only numeric fields whose source type and register quantity match a supported profile 0.2 scalar are included. Writable properties, commands, binary data, strings and width mismatches are excluded. Each acquisition reads a single property; no gaps are read. Observation and vendor polling intervals are not represented.

The source declares `zeroBasedAddressing: false`; the model interprets the source address as one-based and subtracts one for a literal PDU address. Big-endian byte and word order is assumed. Neither assumption nor the field meaning has been independently verified for this firmware or real hardware. Invalid-value encodings are not modeled. Verify mappings, byte order, and firmware against the device before relying on results. Powercenter gateway Unit ID 255 is not supported by the current profile; Unit ID 1 below is a synthetic test value, not its device address.

Validate and export with `modpoll-wot==0.2.0a2`:

```sh
poetry run python -m modpoll_wot validate contrib/siemens/7kn12100mc00/7kn12100mc00.tm.json --kind tm --profile
poetry run python -m modpoll_wot export contrib/siemens/7kn12100mc00/7kn12100mc00.tm.json --host 127.0.0.1 --port 15020 --unit-id 1 -o /tmp/7kn12100mc00.td.json
poetry run python -m modpoll_wot validate /tmp/7kn12100mc00.td.json --kind td --profile
```

The loopback endpoint is a simulation example. Profile validation does not verify device behavior or wire data.
