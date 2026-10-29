# Device examples and vendor references

- [ADAM-5017UH through ADAM-5000L/TCP](adam-5017uh/): first physical-reference
  candidate, confirmed slot 0, eight raw analog input properties.
- [ADAM-6024](adam-6024/): second core I/O candidate, six raw AI, two raw AO,
  two scalar DI and two scalar DO properties in four acquisition blocks.
- `modsim.csv`: existing modpoll 1.x mapping for the built-in simulator.

## One maintained source

Each product folder contains its canonical profile 0.2 `*.tm.json`, vendor PDFs,
source URLs, PDF hashes and assumptions. TDs are generated artifacts:

| File | Purpose |
| --- | --- |
| `*.tm.json` | Maintained source; no deployed endpoint |
| `*.generated.td.json` | Generated project instance with standard Forms and acquisition policy |
| `generated.json` | Source/artifact hashes, generator version and loopback instance parameters |

Register addresses and raw types are in property Forms. Group boundaries remain
explicit in the project acquisition extension. Putting modv fields inside an
extension object does not make that object understandable by standard bindings.
Third-party Consumers use concrete property Forms; they do not need or execute
project grouping for these raw, natively representable properties.

Each TM generates one TD, shared by the project and external Consumers. Its
standard Forms explicitly describe unsigned binary values; node-wot 0.9.2
preserves project extensions but does not execute them. There is no node-wot
specific TD. Grouping/cache behavior is not promised for external Consumers.
Analog values remain unscaled; removing `raw` from filenames does not change
property names, value semantics or the pending physical verification.

## Generate and verify

These examples require the `modpoll-wot==0.2.0a1` candidate tool environment.
The previously released `0.1.0a1` interpreter cannot load profile 0.2. The new
producer has not been published as part of this examples change; use its built
wheel in an isolated developer environment. No local-path or unpublished runtime
dependency is added to modsim.

From this repository, after setting MODPOLL_WOT_WHEEL to the built wheel path:

```sh
mise exec -- python -m venv /tmp/modsim-wot-tools
mise exec -- /tmp/modsim-wot-tools/bin/python -m pip install "$MODPOLL_WOT_WHEEL"
mise exec -- /tmp/modsim-wot-tools/bin/python examples/generate-td.py
mise exec -- /tmp/modsim-wot-tools/bin/python examples/generate-td.py --check
```

The generator delegates all instantiation/export to the common package. It uses
only the documented loopback instance (127.0.0.1:5020, Unit ID 1). For real
endpoints use the common CLI with `--config`, `--host`, `--port`, `--unit-id`,
`--target project` and a new output path; do not commit site-specific TDs as product sources.

Current modsim 1.x still uses its built-in datastore and has no --config option.
Providing these TM/TD artifacts does not implement modsim v2. Vendor PDF originals
and their licensing remain unchanged; offline/wire tests do not prove hardware
mapping or engineering ranges.

See [the manual transport verification record](verification.md) for the
independent fixture and actual node-wot read/write evidence.
