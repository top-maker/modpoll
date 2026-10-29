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

## Run with Docker Compose

From this repository, build and start the current checkout:

```bash
docker compose up -d --build
docker compose logs -f
docker compose down
```

The root [deployment.yaml](deployment.yaml) starts two virtual ADAM devices:
Unit 1 exposes ADAM-5017UH raw inputs; Unit 2 exposes ADAM-6024 raw I/O with
synthetic AO→AI and DO→DI loopback. The values are raw simulation data, not
verified physical measurements. Product models, scenarios and source information
are in [contrib](contrib/README.md).

Compose publishes `127.0.0.1:5020` on the host and uses Docker's
`unless-stopped` restart policy. Each process restart initializes simulation
state again. The deployment listens on `0.0.0.0` inside the container; when run
directly on the host it listens on all interfaces. Change `server.bind` to
`127.0.0.1` to restrict a direct local run. Its advertised TD host is separately
set to `127.0.0.1`; configure the advertised endpoint and port mapping for clients
on other hosts.

Edit `deployment.yaml` or the mounted model/scenario files under `contrib/` and
apply device changes without restarting the container:

```bash
docker compose exec modsim python -m modsim up -f /app/deployment.yaml -d
```

An unchanged device keeps its state; a changed device is replaced. Listener
changes require restarting the container. If an editor replaces the deployment
file, its file bind mount may still reference the old file; use
`docker compose up -d --force-recreate` to refresh it.

## Run locally

Install the source dependencies with `poetry install`, then from the repository
root use:

```bash
poetry run modsim up                  # foreground
poetry run modsim up -d               # start or update in the background
poetry run modsim ps
poetry run modsim logs -f
poetry run modsim up --dry-run
poetry run modsim reset --device analog-input
poetry run modsim export --output-dir ./td
poetry run modsim down
```

The commands default to `deployment.yaml` in the current directory. Use
`-f FILE` to select a deployment; for `logs`, `-f` follows output and
`--file FILE` selects the deployment. In a foreground `up`, Ctrl+C stops a service started
by that invocation; when attached to an existing deployment it only detaches.
`logs -f` also detaches on Ctrl+C. Background processes do not start after a
machine restart unless a process manager is configured. Managed commands require
POSIX (Linux/macOS/WSL); see [managed deployments](docs/managed-deployments.md).

`modsim export` writes TDs using the same model instantiation as the running
simulator. It does not need the server to run. Use `--running` to export the last
successfully applied configuration instead of pending file edits. For TDs inside
the Compose container, run `docker compose exec modsim python -m modsim export
-f /app/deployment.yaml --output-dir /tmp/td`; the output is inside the container.

## Models and scenarios

A deployment has a stable ID per device, a TM path, instance parameters and an
optional scenario. TD IDs and Modbus Unit IDs must be unique. Scenarios define
initial values, seeded generators and bindings; local Python behavior requires
`--allow-scripts`. They do not duplicate the model's register mapping. See
[model configuration](docs/model-validation.md) for the supported profile,
codecs, constraints and behavior hooks.

For a single device without a managed deployment:

```bash
poetry run modsim --config contrib/advantech/adam-5017uh/adam-5017uh-slot-0.tm.json \
  --unit-id 1 --port 5020 \
  --scenario contrib/advantech/adam-5017uh/temperature.sim.json
```

The single-device model runtime currently supports TCP. The unconfigured demo
also supports TCP, UDP, TLS, RTU and ASCII; its datastore is shared by all Unit
IDs. TLS loads `certificates/pymodbus.crt` and `certificates/pymodbus.key` from
the working directory. See [transport details](docs/index.md#unconfigured-demo).

Generated product TDs and their source hashes can be checked with
`poetry run python tools/generate-td.py --check`; omit `--check` to regenerate.

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md) for the v2 workflow and checks. The
repository keeps v1 and v2 release lines separate; no release is implied by a
source change.
