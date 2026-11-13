# Modsim 2.0.0a12 preview

Modsim 2.0.0a12 keeps modpoll-wot 0.6.0a2 and changes how a simulator is reached:

- **Port 5020 by default.** Without `--port`, modsim now listens on 5020 for TCP, UDP and TLS, so the first
  command needs no administrator rights on Linux and macOS. Read it with
  `modpoll --tcp 127.0.0.1 --tcp-port 5020` (modpoll 2.0.0a10). `--port 502` still selects the standard port.
- **Modbus RTU without hardware.** `modsim --config device.tm.json --serial pty` creates a virtual serial
  port on Linux and macOS, prints it together with the matching `modpoll --serial ...` command, and removes
  it on exit. `--serial-link PATH` adds a fixed symbolic link; `--serial PORT` listens on an existing port
  (on Windows, one port of a virtual pair made with a driver such as com0com). Virtual ports ignore baud
  rate and parity. pyserial is now installed with modsim.

## Modsim 2.0.0a11 preview

Modsim 2.0.0a11 pins modpoll-wot 0.6.0a2 and resolves the ModioHub server from the only stored login.

## Modsim 2.0.0a10 preview

Modsim 2.0.0a10 keeps modpoll-wot 0.5.0a1. `modsim login` prints the sign-in link and opens a browser only
where one can be opened; the opener's output no longer fills the terminal, and Ctrl-C cancels with one line.
The login is shared with modpoll 2.0.0a8.

## Modsim 2.0.0a9 preview

Modsim 2.0.0a9 pins modpoll-wot 0.5.0a1 and connects to ModioHub:

- `modsim login` signs in with your browser and `modsim logout` forgets the login. The 7-day tool session is
  kept in `~/.config/modiohub/credentials.json` and is shared with modpoll 2.0.0a7.
- `--config modiohub:<id>@<version>` simulates a custom Thing Model from your ModioHub Workspace (a shared one
  needs no login). Deployment manifests do not accept it.
- It also carries the SIM-06 fixes: only writable points are held after a client write, management requests
  and device builds no longer block the event loop, and `script:` paths stay inside the deployment directory.

## Modsim 2.0.0a8 preview

Modsim 2.0.0a8 loads [simulation data](https://github.com/top-maker/modpoll-wot/blob/main/profile.md#simulation-data)
with `--data` and pins modpoll-wot 0.4.0a1. This preview breaks the previous
command line:

- `--scenario` becomes `--data`; deployment devices use `data:` instead of
  `scenario:`.
- `--initial-file` is removed: put the values in a data document's `initial`.
- Simulation data carries no code. Behavior scripts move out of the data file
  to `--script` (with `--allow-scripts`) or a deployment device's `script:`,
  and their values to the device's `scriptParameters:`.
- A modpoll `--export` snapshot is simulation data, so a device read once can
  be replayed on this computer:

```sh
uvx --prerelease allow modpoll==2.0.0a6 --config device.tm.json --tcp 192.168.1.10 --once --export snapshot.json
uvx --prerelease allow modsim==2.0.0a8 --config device.tm.json --data snapshot.json
```

Scaled values that modpoll exports, such as `230.10000000000002` for a raw
2301 with multiplier 0.1, are served again unchanged. Snapshot points modpoll
could not read keep their defaults and are listed at startup. Snapshots hold
readings of a real device: keep them on your computer.

The `v2.0.0a7` tag points at the same changes but was never published: its
release guard did not yet expect the new snapshot replay CI job.

### Previous preview

#### Modsim 2.0.0a6

Modsim 2.0.0a6 pins modpoll-wot 0.3.0a3, the same interpreter as modpoll
2.0.0a5. Thing Models no longer carry a `modpoll:audit` plan: a TM that still
declares one is rejected as an unsupported root project extension, so modsim
and modpoll accept the same models. Delete the key to migrate. Simulation,
ports and remote loading are unchanged from 2.0.0a5:

```sh
uvx --prerelease allow modsim==2.0.0a6 --config https://example.org/device.tm.json
```

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
