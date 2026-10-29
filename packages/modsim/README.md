# modsim

modsim is a standalone Modbus simulator for device integration and testing.
The v2 development source reads WoT Thing Models (TM), instantiates device
descriptions (TD), and runs independent simulated devices on one Modbus TCP
listener. Models, scenarios, the simulator and the client remain separate.

This README describes the **v2 development branch**. The published `2.0.0a1`
preview predates the managed deployment commands shown below; do not assume an
existing `latest` image or installed package contains the current source.
Stable and preview releases are independent. See [preview notes](docs/preview-notes.md)
and [release process](docs/release-process.md).

## Install from source

The v2 managed deployment commands are available in the development source;
they are not included in the published `2.0.0a1` release. Clone the `v2`
branch and install its dependencies with Poetry:

```bash
git clone --branch v2 https://github.com/top-maker/modsim.git
cd modsim
poetry install
```

## Run locally

From the root directory, start the example deployment and check its status:

```bash
poetry run modsim up -d
poetry run modsim ps
```

The commands use `examples/deployment.yaml` by default. The example starts two
virtual ADAM devices: Unit 1 exposes ADAM-5017UH raw inputs; Unit 2 exposes
ADAM-6024 raw I/O with synthetic AO→AI and DO→DI loopback. These are simulation
values, not verified physical measurements. Models, scenarios and source
information are in [contrib](contrib/README.md).

The deployment binds to all interfaces by default; set `server.bind` to
`127.0.0.1` in `examples/deployment.yaml` to restrict a direct local run.

Useful commands for managing the deployment:

```bash
poetry run modsim logs -f
poetry run modsim up --dry-run
poetry run modsim reset --device adam-5017uh
poetry run modsim export
poetry run modsim down
```

Export writes all TDs to `output/` in the root directory by default; this
directory is ignored by Git. Use `-o FILE` for one TD or `--output-dir DIR` to
choose another directory.

Use `-f FILE` to select another deployment. In `logs`, `-f` follows output;
use `--file FILE` to select the deployment. `up` runs in the foreground by
default; `-d` runs it in the background. Ctrl+C stops a service started by a
foreground `up`, but only detaches from an existing deployment or `logs -f`.
Background services do not restart after a machine reboot unless managed by a
process manager. Managed commands require POSIX (Linux/macOS/WSL); see
[managed deployments](docs/managed-deployments.md).

`modsim export` reads the current deployment file and does not require a
running simulator. Use `--running` only when you need the last successfully
applied configuration instead of current file contents. That option connects to
the managed runtime in the same environment, so a Poetry command can only read
a Poetry-started deployment; for Docker Compose, run it inside the container.

## Run with Docker Compose

From the `examples/` directory, build and start the current source:

```bash
docker compose up -d --build
docker compose logs -f
```

Compose publishes Modbus TCP only on host `127.0.0.1:5020` and restarts the
container unless stopped. Each restart resets simulation state. TDs advertise
`127.0.0.1` by default; configure the advertised host and port mapping when
clients connect from another machine.

The deployment and model/scenario files are mounted from the repository.
`docker compose up -d` starts the configured deployment; do not run `modsim up`
again just to start it. After editing the mounted deployment file, apply the
updated configuration to the running simulator with:

```bash
docker compose exec modsim python -m modsim up -f /app/examples/deployment.yaml -d
```

An unchanged device keeps its state; a changed device is replaced. Listener
changes require a container restart. If you replace the deployment file itself,
run `docker compose up -d --force-recreate` to refresh its bind mount. Export
all running TDs directly into the host's `examples/td/` directory. The Compose
file maps the default output directory to that host directory. Run this from
the `examples/` directory:

```bash
docker compose exec modsim python -m modsim export --running
```

This creates one `*.td.json` file per device in `examples/td/`.

Stop the Compose deployment with `docker compose down`.

## Example: test modpoll against modsim

This example uses modpoll v2 (`modpoll==2.0.0a2`) and the local modsim source.
Export all TDs from the current deployment file. Run from the root directory;
modsim does not need to be running:

```bash
poetry run modsim export
```

In another terminal, from the root directory, read the exported TD:

```bash
modpoll --once --interval 0 --tcp 127.0.0.1 --tcp-port 5020 \
  --config ./output/adam-6024.td.json --export ./adam-6024-snapshot.json
```

If you need the last applied configuration from a Docker Compose deployment,
use the Compose export command above and point modpoll to
`./examples/td/adam-6024.td.json` instead.

The TD selects Unit ID 2. On a fresh deployment, `adam6024_raw` reports
`AO0_RAW: 100` and `AI0_RAW: 100`; values may differ if previously written.
The command reads the exported TD and connects to modsim on the host port.

### Optional: write via MQTT

Start a temporary local broker and a continuously running modpoll process:

```bash
docker run --rm -d --name modpoll-demo-mqtt -p 127.0.0.1:1883:1883 \
  eclipse-mosquitto:2 mosquitto -c /mosquitto-no-auth.conf
modpoll --interval 0 --rate 1 --tcp 127.0.0.1 --tcp-port 5020 \
  --config ./adam-6024.td.json --mqtt-host 127.0.0.1 --mqtt-port 1883
```

After modpoll connects, publish a non-retained write to the topic named for
the TD's `title` (`adam6024_raw`):

```bash
docker exec modpoll-demo-mqtt mosquitto_pub -h 127.0.0.1 \
  -t modpoll/adam6024_raw/set \
  -m '{"object_type":"holding_register","address":10,"value":432}'
```

Run the one-shot modpoll command again. `AO0_RAW` and loopback `AI0_RAW`
should both read `432`. This synthetic raw value does not verify the physical
device's range or behavior. The example broker has no authentication and is
published only on host loopback; port 1883 must be available.

Stop modpoll with Ctrl+C, stop the broker if used (`docker stop
modpoll-demo-mqtt`), then stop modsim with `poetry run modsim down` or stop the
Compose deployment with `docker compose down`.

## Models and scenarios

A deployment has a stable ID per device, a TM path, instance parameters and an
optional scenario. TD IDs and Modbus Unit IDs must be unique. Scenarios define
initial values, seeded generators and bindings; local Python behavior requires
`--allow-scripts`. They do not duplicate the model's register mapping. See
[model configuration](docs/model-validation.md) for the supported profile,
codecs, constraints and behavior hooks.

For a single device without a managed deployment:

```bash
poetry run modsim --config contrib/advantech/adam-5017uh/adam-5017uh.tm.json \
  --unit-id 1 --port 5020 \
  --scenario contrib/advantech/adam-5017uh/simulation/adam-5017uh.sim.json
```

The single-device model runtime currently supports TCP. The unconfigured demo
also supports TCP, UDP, TLS, RTU and ASCII; its datastore is shared by all Unit
IDs. TLS loads `certificates/pymodbus.crt` and `certificates/pymodbus.key` from
the working directory. See [transport details](docs/index.md#unconfigured-demo).

The checked-in ADAM-6024 TD and its source hash can be checked with
`poetry run python tools/generate-td.py --check`; omit `--check` to regenerate.

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md) for the v2 workflow and checks. The
repository keeps v1 and v2 release lines separate; no release is implied by a
source change.
