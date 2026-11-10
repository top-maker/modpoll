# Modsim 2.0.0a6 preview

Modsim 2.0.0a6 pins modpoll-wot 0.3.0a3, the same interpreter as modpoll
2.0.0a5. Thing Models no longer carry a `modpoll:audit` plan: a TM that still
declares one is rejected as an unsupported root project extension, so modsim
and modpoll accept the same models. Delete the key to migrate. Simulation,
ports and remote loading are unchanged from 2.0.0a5:

```sh
uvx --prerelease allow modsim==2.0.0a6 --config https://example.org/device.tm.json
```

### Previous preview

#### Modsim 2.0.0a5

Without `--port`, modsim now listens on the standard Modbus port: 502 for TCP
and UDP, 802 for Modbus/TLS. A simulator started from a ModioHub Thing Model is
then read with `modpoll --tcp 127.0.0.1`, without `--tcp-port`:

```sh
uvx --prerelease allow modsim==2.0.0a5 --config https://example.org/device.tm.json
```

Linux, and macOS when binding to `127.0.0.1`, reserve ports below 1024 for
administrators. modsim then exits before starting and explains how to rerun it
with sudo (`sudo "$(command -v uvx)" modsim ...`) or choose a port above 1023,
for example `--port 5020`. Managed deployments keep their explicit server port.
This preview still pins modpoll-wot 0.2.0a4.

#### Modsim 2.0.0a4

Remote models and scenarios load directly from a site such as ModioHub:

```sh
uvx --prerelease allow modsim==2.0.0a4 --config https://example.org/device.tm.json \
  --scenario https://example.org/device.sim.json --bind 127.0.0.1 --port 5020
```

HTTPS requests identify themselves as `modsim/<version>`, because some CDNs reject
the default Python agent. `--scenario` accepts an HTTPS URL; a remote scenario
cannot name a behavior script. This preview still pins modpoll-wot 0.2.0a4.


#### Modsim 2.0.0a3


This preview pins modpoll-wot 0.2.0a4. A local TCP simulator can load a full
profile 0.2 TM with an audit plan or its independently derived public audit TM.
Tests seed the same known values and verify the public model exposes only the
selected read spans.

#### Modsim 2.0.0a2

This candidate uses published modpoll-wot 0.2.0a2 and immutable modbus-models-v1
inputs. Device mappings and contribution workflows moved to a data repository,
now [Open Modbus Catalog](https://github.com/top-maker/open-modbus-catalog);
examples pin a full data commit and individual content hashes. Vendor originals
are not copied. The tool and data releases remain independent.

Managed deployment version 2 supports local lifecycle and isolation on POSIX.
Single-device foreground mode supports fixed HTTPS TMs and local scenarios;
scripts require explicit --allow-scripts. Catalog acceptance compares raw Modbus
bytes, public modpoll 2.0.0a2 and node-wot 0.9.2 with asymmetric uint16 inputs,
and detects a deliberately wrong byte order. This is software evidence, not
hardware or engineering-unit certification.

Release gates cover independent wheel single-device startup/read/stop on Linux,
macOS and Windows. Managed deployments remain POSIX-only; Windows uses foreground
mode or WSL. A candidate is not accepted until its exact CI and preview publish,
image, docs and source-independent acceptance jobs all pass.

Expected install after publication: `uv tool install --prerelease allow modsim==2.0.0a2`.
The explicit preview image is `topmaker/modsim:2.0.0a2`; stable latest aliases stay
unchanged. Older 2.0.0a1 artifacts and historical contrib URLs remain immutable.
