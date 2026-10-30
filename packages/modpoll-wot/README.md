# modpoll-wot (experimental)

An independently versioned TM/TD configuration interpreter for Modpoll and future
compatible consumers. No Modbus execution, scheduler or MQTT service is included.

The following CLI is available in the next release; it is not in 0.2.0a1.

```sh
modpoll-wot generate --title "Meter" -o meter.tm.json
modpoll-wot validate meter.tm.json
modpoll-wot validate meter.tm.json --kind tm --profile
modpoll-wot export meter.tm.json --host 127.0.0.1 --port 5020 --unit-id 7 -o meter.td.json
modpoll-wot validate meter.td.json
```

Use `modpoll-wot --help` and `modpoll-wot validate --help` for options.
Structure validation is offline and rejects duplicate JSON keys; it does not
check JSON-LD, references, device behavior or complete W3C conformance. Type is
detected from the document, so use `--kind tm` for a known TM whose type might
be missing. `--profile` checks the executable subset, accepting instance options
and `--param NAME=JSON` when needed. The starter is a standard TM skeleton;
add profile 0.2 mappings before executable validation or export. Export accepts
`--target node-wot-0.9.2` for the documented subset and never overwrites files.

See [profile.md](profile.md) for the current profile and
[CONTRACT.md](CONTRACT.md) for retained 0.1 profile support.

The loader validates bundled W3C TM/TD 1.1 schemas, the project extension
schema, and acquisition semantics. It does not execute Modbus requests.

```python
from modpoll_wot.loading import load_model
model = load_model("examples/modsim.tm.json", unit_id=1)
```

The application adapter is connected to the existing Modpoll poll/decode/output engine. Run checks from the repository root:

```sh
PYTHONPATH=packages/modpoll-wot python -m unittest discover -s packages/modpoll-wot/tests
```

The bundled W3C schemas identify themselves as 1.1-12-March-2025, retrieved from
https://www.w3.org/2022/wot/td-schema/v1.1 and
https://www.w3.org/2022/wot/tm-schema/v1.1. Standard validation does not
establish device correctness.

Version 0.2.0a1 supports [profile 0.2](profile.md): standard Form mappings,
explicit blocks, per-property decoding and TM-to-TD export. Profile 0.1 remains
available for existing configurations.
