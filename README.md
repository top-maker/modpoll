> **2.x development branch.** This checkout accepts v1 CSV and WoT TM/TD JSON using profile 0.2; `--config` detects the format from the content. Install the current preview with `uv tool install --prerelease allow 'modpoll[serial]==2.0.0a7'`; stable 1.x remains available with `uv tool install 'modpoll<2'`. For development, run `make install`, then prefix project commands with `uv run`.

# Modpoll - A New Command-line Tool for Modbus and MQTT

[![Release](https://img.shields.io/github/v/release/top-maker/modpoll)](https://img.shields.io/github/v/release/top-maker/modpoll)
[![Build status](https://img.shields.io/github/actions/workflow/status/top-maker/modpoll/main.yml?branch=main)](https://github.com/top-maker/modpoll/actions/workflows/main.yml?query=branch%3Amain)
[![License](https://img.shields.io/github/license/top-maker/modpoll)](https://img.shields.io/github/license/top-maker/modpoll)
[![Downloads](https://static.pepy.tech/badge/modpoll/week)](https://pepy.tech/project/modpoll)


> Learn more about *modpoll* usage at [documentation](https://top-maker.github.io/modpoll) site.

## Motivation

The idea for creating this tool originated from my need to efficiently check new devices during site surveys. These surveys are often time-constrained and space-limited, with on-site work adding to the pressure. In such situations, a portable Swiss Army knife toolkit becomes a valuable companion.

This tool can be easily deployed on a Raspberry Pi or similar embedded devices, polling data from a Modbus network or connected devices. Users can choose to log the data locally or publish it to an MQTT broker for further troubleshooting.

The MQTT broker can be set up either on the same Raspberry Pi or in the cloud. Once data is successfully published, users can subscribe to the relevant MQTT topics and conveniently view the data on their smartphones.

<p align="center">
  <img src="docs/site/assets/modpoll-usage.png">
</p>

Moreover, you can also run this tool continuously on a server as a Modbus-MQTT gateway, i.e. polling from local Modbus devices and forwarding data to a centralized cloud service.

In fact, *modpoll* helps to bridge between the traditional field-bus world and the new IoT world.

> 💡 **Tips:** This tool is designed to be a standalone executable application, which works out-of-the-box on Linux/macOS/Windows. If you are looking for a Modbus python library, please consider the following great open-source projects, [pymodbus](https://github.com/riptideio/pymodbus) or [minimalmodbus](https://github.com/pyhys/minimalmodbus)


## Feature

- Support Modbus RTU/TCP/UDP devices
- Show polling data for local debugging, like a typical modpoll tool
- Publish polling data to MQTT broker for remote debugging, especially on smart phone
- Export polling data to local storage for further investigation
- Provide docker solution for continuous data polling use case


## Installation

This tool requires Python 3.10+ (Ubuntu 22.04+ or equivalent) and is available on the [Python Package Index](https://pypi.org/). Install it with uv. Ubuntu 20.04 and Python 3.8 are no longer supported.

### Using uv

Install *modpoll* using the following command,

```bash
uv tool install --prerelease allow "modpoll==2.0.0a7"
```

Optionally, [pyserial](https://pyserial.readthedocs.io/) library can be installed for Modbus-RTU communication,

```bash
uv tool install --prerelease allow 'modpoll[serial]==2.0.0a7'
```

Upgrade the tool via the following command,

```bash
uv tool install --upgrade --prerelease allow "modpoll<3"
```

The same commands work on Windows PowerShell; uv manages the isolated tool environment.

## Quickstart

Verify modpoll against the already deployed public Modbus TCP simulator. No
local modsim installation or Docker container is needed:

```bash
modpoll --once \
  --tcp modsim.topmaker.net --tcp-port 502 \
  --config examples/modsim.tm.json
```

### Modbus ASCII and framers

- Serial transports: use `--serial PORT --framer ascii` (alias: `--rtu` still accepted); pyserial URLs such as `socket://host:port` and `rfc2217://host:port` work for serial-over-TCP tunnels.
- Serial supports framers `ascii` and `rtu` (pymodbus defaults to RTU if `--framer default`). Binary framer is no longer supported in pymodbus 3.9+.

### Prepare a WoT configuration

Use [examples/modsim.tm.json](examples/modsim.tm.json) for the simulator model or
[examples/modsim.generated.td.json](examples/modsim.generated.td.json) for its
generated local TCP instance.
Both preserve the four original blocks and 37 output references. `--unit-id`
overrides the Unit ID declared consistently in Forms (fallback 1); a concrete TD's Forms must agree before overrides.
The existing transport, polling, output and MQTT arguments remain available.

See the [current profile](https://github.com/top-maker/modpoll-wot/blob/main/profile.md) for field mapping,
access flags, byte order, multiplier semantics and supported limits; the
[execution contract](https://github.com/top-maker/modpoll-wot/blob/main/CONTRACT.md) defines the profile 0.2-only input policy.
The configuration loader detects the format from the content and reports invalid
model fields before polling. Each model describes one device; use multiple
`--config` paths for multiple devices. Give each model a unique `title`, which is
the output device name. Existing v1 CSV configurations load through the same
`--config` argument; no separate flags are needed.

Physical RS485 polling has also been verified by the maintainer with an Eastron
meter (2026-10-28). See [validation](docs/validation.rst) for the evidence scope and
[contributed mappings](contrib/README.md) for vendor references.

For a complete local simulator/MQTT demonstration, use the repository's
[Docker Compose example](examples/README.md).

### Read a device and write a verification report

Adding `--report` to a normal read verifies the Thing Model on real hardware: every point is read once,
read-only, without retries and with a timeout of at most 10 seconds, so a lost request is a result and not
something to repeat. MODEL is a local TM/TD file, an http(s) URL or a `modiohub:<id>@<version>` Workspace
reference. `--report FILE` writes the verification report (`-` prints it); bare `--report` asks where to
save, whether the values look right, and whether to upload:

```sh
modpoll --config examples/modsim.tm.json --tcp 192.168.1.20 --unit-id 3 --report report.json
```

The report records, per point, whether the read worked (`ok`, a Modbus `exception` with its code,
`no-response`, or `not-tested` when the answer could not be decoded) and your judgment of the value:
`--confirm POINT...` (or `all`) and `--reject POINT...` for values you compared with the device, otherwise
`unchecked`. The report holds no address, Unit
ID, serial number or value; review it before sharing. It is checked with
[modpoll-wot](https://github.com/top-maker/modpoll-wot) (`modpoll-wot validate-report report.json --model
model.tm.json`), and `--export` still writes the snapshot of the same read. ModioHub resolves the product
from the model fingerprint, so you never name the product. The exit
code is 1 unless every point was read.

### Sign in to ModioHub, read a Workspace Thing Model and upload the report

`modpoll login` signs in with your browser: it prints a code and an address (and opens the address where a
browser can open), you confirm the code there, and the 7-day tool session is kept in a file only you can read
(`~/.config/modiohub/credentials.json`, or `%APPDATA%\modiohub` on Windows). modsim uses the same file, so
signing in with either tool signs in both. `MODIOHUB_TOKEN` in the environment replaces the file for scripts,
`MODIOHUB_URL` selects another server, and `login` and `logout` take `--server URL` for the same. `modpoll logout` forgets the login on this computer;
revoke the session in your ModioHub settings to end it on the server.

Once signed in, `--config modiohub:<id>@<version>` (the version is a number or `latest`) reads one
of your custom Thing Models. A shared one needs no login. Verifying it names the Workspace model in the
report, and `modpoll --config ... --upload` shows the report and, after you confirm (or with `--yes`),
uploads it; without a login the sign-in flow starts right there:

```sh
modpoll --config modiohub:k3x9f2m7q4a8n5bd@latest --tcp 192.168.1.20 --upload
```

### MQTT data and write behavior

The local example above uses the `adam6024_raw` TD title for its default topics:
`modpoll/adam6024_raw/data` for samples and `modpoll/adam6024_raw/set` for
write commands. The publish, subscribe and diagnostics topic patterns are
configurable; see the [MQTT documentation](docs/site/usage.rst).

Writes use literal Modbus PDU addresses and raw values. Holding-register arrays
use FC16 and must contain 1–123 unsigned 16-bit values within the address range.
Invalid, oversized, malformed, ambiguous or retained write messages are ignored
and logged. Brokers can clear the retained flag on live forwarding, so configure
the broker not to retain commands on the set topic; QoS does not make a write
exactly once.

When a sample is invalid in a poll cycle, modpoll omits it from MQTT output and
writes `null` for that point in the JSON snapshot. Snapshots from multiple
configuration files are combined and replaced atomically. When `--timestamp` is
enabled, the timestamp is the start time of the poll cycle in Unix seconds; a
device with a point named `timestamp` cannot use it. A snapshot is
[simulation data](https://github.com/top-maker/modpoll-wot/blob/main/profile.md#simulation-data),
so `modsim --config device.tm.json --data snapshot.json` replays it locally.


## Run with docker

A docker image has been provided for user to directly run the tool without local installation,

  ```bash
  docker run --rm topmaker/modpoll:2.0.0a7
  ```

It shows the version of the tool by default.

On Linux, host networking connects the container to a simulator on the host.
Mount the JSON configuration into the container; ``--daemon`` suppresses tables.

If you want to load a local configure file, you need to mount a local folder onto container volume,
for example, if the child folder `examples` contains the config file `modsim.tm.json`, we can use it via the following command,

  ```bash
  docker run --rm --network host -v "$(pwd)/examples:/app/examples:ro" topmaker/modpoll:2.0.0a7 \
    modpoll -d \
      --tcp 127.0.0.1 --tcp-port 5020 \
      --config /app/examples/modsim.tm.json
  ```


## Example Use Cases

- Connect to Modbus TCP device

  ```bash
  modpoll \
    --tcp 192.168.1.10 \
    --config examples/modsim.tm.json
  ```

- Connect to Modbus serial device

  ```bash
  modpoll \
    --serial /dev/ttyUSB0 \
    --serial-baud 9600 \
    --config examples/modsim.tm.json
  ```

- Connect to Modbus TCP device and publish data to MQTT broker

  ```bash
  modpoll \
    --tcp 127.0.0.1 --tcp-port 5020 \
    --mqtt-host broker.emqx.io \
    --config examples/modsim.tm.json
  ```

- Connect to Modbus TCP device and export a local JSON snapshot

  ```bash
  modpoll \
    --tcp 127.0.0.1 --tcp-port 5020 \
    --export data.json \
    --config examples/modsim.tm.json
  ```

- Replay the snapshot with modsim on this computer (keep snapshots of real
  devices local)

  ```bash
  modsim --config examples/modsim.tm.json --port 5020 --data data.json
  ```

> Refer to the [documentation](https://top-maker.github.io/modpoll) site for more details about the configuration and examples.

> *If you find this tool useful, please support us by starring 🌟 our repository to encourage further improvements.*

## Credits

The implementation of this project is heavily inspired by the following two projects:
- https://github.com/owagner/modbus2mqtt (MIT license)
- https://github.com/mbs38/spicierModbus2mqtt (MIT license)

Thanks to Max Brueggemann and Oliver Wagner for their great work.


## License

MIT © 2021-2026, Ying Shaodong
