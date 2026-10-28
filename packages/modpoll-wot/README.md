# modpoll-wot (experimental)

An independently versioned TM/TD configuration interpreter for Modpoll and future
compatible consumers. No Modbus execution, scheduler or MQTT service is included.

```sh
pip install modpoll-wot==0.1.0a1
python -m modpoll_wot meter.tm.json
```
See CONTRACT.md for the executable 0.1 subset and 1.x field mapping.

The loader validates bundled W3C TM/TD 1.1 schemas, the project extension
schema, and acquisition semantics. It does not execute Modbus requests.

```python
from modpoll_wot.loading import load_model
model = load_model("examples/modsim.tm.json", kind="tm", unit_id=1)
```

The application adapter is connected to the existing Modpoll poll/decode/output engine. Run checks from the repository root:

```sh
PYTHONPATH=packages/modpoll-wot python -m unittest discover -s packages/modpoll-wot/tests
```

The bundled W3C schemas identify themselves as 1.1-12-March-2025, retrieved from
https://www.w3.org/2022/wot/td-schema/v1.1 and
https://www.w3.org/2022/wot/tm-schema/v1.1. Standard validation does not
establish device correctness.

A source-only [standards-first pilot](pilot.md) explores Form-based mappings and
TM-to-TD generation separately from the released 0.1 contract.
