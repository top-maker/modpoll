# modpoll, modsim and modpoll-wot

**Documentation:** <https://top-maker.github.io/modpoll/v2/>

This branch (`v2`) holds three tools that read, simulate and describe Modbus devices with W3C WoT Thing Models.
They are released separately to PyPI and share one uv workspace and one lock file.

| Package | What it does | Source |
| --- | --- | --- |
| [modpoll](https://pypi.org/project/modpoll/) | Reads Modbus TCP and RTU devices from a Thing Model, publishes to MQTT and writes verification reports | [packages/modpoll](packages/modpoll) |
| [modsim](https://pypi.org/project/modsim/) | Simulates a Modbus device from a Thing Model, over TCP or a virtual serial port | [packages/modsim](packages/modsim) |
| [modpoll-wot](https://pypi.org/project/modpoll-wot/) | The executable Thing Model profile, fingerprints and report schemas both tools share | [packages/modpoll-wot](packages/modpoll-wot) |

modpoll 1.x lives on the `main` branch. Earlier modsim and modpoll-wot history is part of this branch;
their former repositories are archived.

## Development

```bash
uv sync --all-packages --all-extras --all-groups
cd packages/modpoll && uv run pytest
```

Each package keeps its own `Makefile`, tests and release notes. `integration/` runs this commit's modsim and
modpoll against each other with modpoll-wot's conformance model, over Modbus TCP and RTU on a virtual serial
port, and reads a round-trip matrix (data type × byte and word order × multiplier × boundary value) with
modpoll, pymodbus and node-wot (`uv run pytest integration` after the sync above; node-wot needs
`npm ci --prefix packages/modpoll/tools/wot-interop`). A release is a tag named after the package,
for example `modsim-v2.0.0a13`, which runs that package's release workflow.

The documentation site for all three packages is built from `docs/` with Sphinx, MyST and Furo. Its dependency
group needs Python 3.13 or later:

```bash
uv sync --only-group docs --python 3.14
uv run --no-sync sphinx-build -W -b html docs docs/_build/html
uv run --no-sync sphinx-autobuild docs docs/_build/html
```

Pull requests build it with warnings as errors and check its links. Each package release publishes it from the
release tag to `/v2/`; a modpoll-wot release also publishes `/vocab/wot-modbus/`.
