# Siemens 3nx8-x-02 read-only numeric subset

[3nx8-x-02.tm.json](3nx8-x-02.tm.json) contains 17 of 85 source properties. It is a partial model derived from the [original Siemens TM](specs/Siemens_3NX8.02_FW-V7.3.tm.jsonld) (FW-V7.3, Apache-2.0). Of the 68 excluded properties, 37 are writable or write-only, 26 have non-numeric schemas, and 5 have a raw type width that differs from the register quantity. Categories are counted in that order and are mutually exclusive. The [2023 system manual](specs/sentron-system-manual-2023.pdf) is an older reference and does not establish all FW-V7.3 mappings. See [source record](specs/sources.json).

Only read-only numeric fields whose source type and register quantity match a supported profile 0.2 scalar are included. Writable properties, commands, binary data, strings and width mismatches are excluded. Each acquisition reads a single property; no gaps are read. Observation and vendor polling intervals are not represented.

The source declares `zeroBasedAddressing: false`; the model interprets the source address as one-based and subtracts one for a literal PDU address. Big-endian byte and word order is assumed. Neither assumption nor the field meaning has been independently verified for this firmware or real hardware. Invalid-value encodings are not modeled. Verify mappings, byte order, and firmware against the device before relying on results.

Validate and export with `modpoll-wot==0.2.0a2`:

```sh
uv run python -m modpoll_wot validate contrib/siemens/3nx8-x-02/3nx8-x-02.tm.json --kind tm --profile
uv run python -m modpoll_wot export contrib/siemens/3nx8-x-02/3nx8-x-02.tm.json --host 127.0.0.1 --port 15020 --unit-id 1 -o /tmp/3nx8-x-02.td.json
uv run python -m modpoll_wot validate /tmp/3nx8-x-02.td.json --kind td --profile
```

The loopback endpoint is a simulation example. Profile validation does not verify device behavior or wire data.
