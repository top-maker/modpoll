# modpoll-wot (experimental)

An independently versioned TM/TD configuration interpreter for Modpoll and future
compatible consumers. No Modbus execution, scheduler or MQTT service is included.

```sh
pip install modpoll-wot==0.2.0a1
python -m modpoll_wot meter.tm.json
```
See [profile.md](profile.md) for the current 0.2 profile and
[CONTRACT.md](CONTRACT.md) for retained 0.1 compatibility.

The installed `modpoll-wot` command offers separate structure and executable
profile checks. These commands are included in the next release, not 0.2.0a1:

```sh
modpoll-wot generate tm --title "Meter" --output meter.tm.json
modpoll-wot validate meter.tm.json --kind tm
modpoll-wot validate meter.tm.json --kind tm --profile
modpoll-wot generate td --input meter.tm.json --host 127.0.0.1 --port 5020 --unit-id 7 --output meter.td.json
modpoll-wot validate meter.td.json --kind td
```

The starter TM contains no Modbus mappings and is not executable until edited
to conform to profile 0.2. TD generation requires an executable profile 0.2 TM
and any needed `--param NAME=JSON` bindings. Output files are never overwritten.
Validation is offline; schema success only checks structure, not JSON-LD,
references, device correctness or complete W3C conformance. `--kind auto`
detects TM via its top-level `tm:ThingModel` type and otherwise selects TD;
use `--kind tm` when checking a known TM. `--profile` adds project constraints
and accepts `--host`, `--port`, `--unit-id`, and `--param`. The original
`python -m modpoll_wot --config ...` interface remains supported.

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
