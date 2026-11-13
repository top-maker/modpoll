# modpoll, modsim and modpoll-wot

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

Each package keeps its own `Makefile`, tests and release notes. A release is a tag named after the package,
for example `modsim-v2.0.0a13`, which runs that package's release workflow.
