# Model-driven simulation

The v2 source uses the published, exact `modpoll-wot==0.2.0a2` dependency.
Install with `uv sync --all-groups`. Model parsing and TM instantiation belong to that
shared package; Modsim owns state and protocol execution.

## One device

```bash
uv run modsim --config examples/models/products/advantech/adam-5017uh/model.tm.json \
  --unit-id 1 --port 5020 \
  --data examples/models/products/advantech/adam-5017uh/model.sim.json
```

Without `--port`, the listener uses 502, which needs administrator rights on
Linux and on macOS for `127.0.0.1`; modsim then explains how to rerun with sudo
or choose a port above 1023.

`--config` also accepts HTTPS model URLs. GitHub `blob` links are converted to
raw file URLs. Prefer a tag or commit SHA for repeatable runs; branch URLs change.
Downloads have a 15-second timeout and a 1 MiB limit, and use the shared bounded
JSON loader. Only models are downloaded; no script is fetched or executed from a
model. JSON-LD context URLs are vocabulary identifiers, not execution sources.

The configured runtime supports profile 0.2 integer types (16/32/64-bit,
signed/unsigned), IEEE float16/32/64, fixed-capacity UTF-8 strings, register and
physical scalar booleans, physical boolean arrays, legacy register bool/bool8/
bool16 arrays, register bit selectors and explicit legacy-MSB packed bit payloads.
Byte and word ordering follow the shared contract; legacy packed bit numeric
payloads ignore word ordering, and packed strings ignore both, matching Modpoll.

Initialization, script updates, generators and Modbus writes use the same codec.
Integer-wire multipliers are inverted with exact rational arithmetic: values that
require fractional raw integers or overflow are rejected instead of truncated.
Negative factors are supported. A zero factor can only encode engineering zero,
using raw zero. IEEE values use their representable wire precision; startup
reports and `device.get` return the decoded value. Model constraints apply after
quantization too: an unrepresentable exact `const` is rejected. Numeric initial
values use bounded candidates and arithmetic, not enumeration of 32/64-bit ranges.
Complex constraints may require an explicit initial value/default/enum.

Strings must fit their UTF-8 byte capacity, use zero padding and cannot end in
NUL (consumers strip trailing NULs). Physical bit arrays have their declared
length. Legacy register bool arrays retain the consumer's byte/LSB layout and
preserve unused padding. No engineering-unit conversion is guessed for raw ADAM
channels. Profile 0.2 is required; the unconfigured demonstration is unchanged.

## Managed deployments

For repeatable startup and runtime updates, use deployment version 2 and
`modsim up`. See [managed deployments](managed-deployments.md) for the YAML
contract, TM parameters, dynamic device lifecycle and TD export.
The ADAM lab example starts two independent devices on one listener:

```bash
uv run modsim up -f examples/deployment.yaml
```

Paths in deployment files, including data and script paths, are relative to the
deployment directory. Unit IDs and TD identities must
be unique. Unknown addresses or Unit IDs never inherit another device's state.

## Simulation data

`--data` takes a local path or HTTPS URL of simulation data, defined by
[modpoll-wot](https://github.com/top-maker/modpoll-wot/blob/main/profile.md#simulation-data).
Version `"1"` fields:

| Field | Meaning |
| --- | --- |
| `initial` | Property-name/value static values, the default |
| `tick` | Update interval in seconds, default 1, minimum 0.001 |
| `seed` | Per-instance random seed, default 0 |
| `generators` | Property-name to generator specification |
| `bindings` | Target property to source property for synthetic loopback |
| `writePolicy` | `hold` (default) or `overwrite` for generated properties |

Simulation data carries no code. A modpoll `--export` snapshot is accepted as
well: the entry titled like the model, or the only entry, becomes `initial`;
points modpoll could not read (`null`) keep their defaults and are logged.
Scaled values are accepted when they are exact decimal multiples of the
multiplier or exactly the float modpoll exports, so a snapshot replays
unchanged.

Generators: `constant` (`value`); `sine` (`center`, `amplitude`, positive `period`);
`ramp` (`start`, `rate`, `minimum`, `maximum`, clamped to bounds);
`noise` (`minimum`, `maximum`, uniform seeded noise). Integer-property noise
uses integer sampling to preserve the full 64-bit range.
Numeric generators round to the nearest integer for integer model properties.
Boolean channels can use constant values, bindings or scripts. All updates must
satisfy the model's schema and raw encoding bounds. Unknown properties are errors.
Binding chains and cycles are rejected; use a script for ordered dependencies.

Initialization order: model defaults/type fallback → data `initial` →
CLI `--initial` → script `initialize` → first dynamic update at elapsed 0.
Single-device startup logs include the final initialized values; raw values are
synthetic unless the contribution explicitly documents their source.

On each tick: generators → script `tick` → bindings. Modbus writes validate the
whole request, then run `on_write` and bindings before responding. Invalid write
requests or failed write hooks roll back register changes. Partial register
writes re-decode every overlapping property, including properties whose first
register was not touched. Batch updates and alias constraints are checked before
commit. Bit-field updates preserve neighboring bits. Protocol writes may not
change read-only/reserved bits; a writable bit sharing a register with read-only
bits can be changed while preserving those bits. Reads that would expose a
write-only field are rejected, while FC5/6 write echoes remain supported.
Model read-only measurements may be changed internally but cannot be written by clients.
`hold` stops a generator for a property after a valid client write until restart;
`overwrite` permits the next tick to replace it. Scripts define their own write
response and may deliberately overwrite values.

## Local Python behaviors

```bash
uv run modsim --config examples/models/products/advantech/adam-5017uh/model.tm.json \
  --script behavior.py --allow-scripts
```

Optional synchronous hooks:

```python
def initialize(device):
    device.set("AI0_RAW", 100)


def tick(device, elapsed, dt):
    device.set("AI0_RAW", 100 + int(elapsed) % 100)


def on_write(device, changes):
    if "AO0_RAW" in changes:
        device.set("AI0_RAW", changes["AO0_RAW"])
```

Use `get(name)`, `set(name, value)` and `set_many({...})`. Batch updates validate
all values before changing cells. Hooks run on the server event loop and must not
block; async hooks are rejected. Python is ordinary local code, enabled explicitly
by `--allow-scripts`. Each device loads its own module instance. In single-device
`--config` mode, periodic behavior errors stop the server. In managed mode, an
error takes only that device offline and is reported by `ps`. SIGINT/SIGTERM
cancel updates and close the server.

The sample loopback is an explicit synthetic assumption, not a claim that real
ADAM hardware automatically connects AO to AI or DO to DI. No fault injection,
recording/replay, multi-listener runtime or remote behavior execution is included.

Prepare pinned example inputs from the repository root with
`uv run python tools/fetch-models.py`; see `examples/model-source.yaml`.
