# Managed deployments

Managed commands run a local, single-listener deployment of several devices.
They currently require POSIX (Linux, macOS or WSL); the existing
flag-based server entry point remains available on other platforms.

## Start and reconcile

```bash
modsim up -f examples/deployment.yaml -d
modsim ps -f examples/deployment.yaml
modsim up -f examples/deployment.yaml --dry-run
modsim up -f examples/deployment.yaml
modsim down -f examples/deployment.yaml
```

All commands default to `examples/deployment.yaml` in the current directory. `up` runs in
the foreground on first startup; `-d` starts a detached process. Later `up`
commands update that process and follow its logs; use `-d` to return immediately.
Interrupting the original foreground process stops its deployment. Interrupting
an attached `up` or `logs --follow` disconnects that viewer while the existing
deployment continues. `down` waits for cleanup; repeating it is harmless.

Each deployment has a `name`, defaulting to the deployment directory name. Names
identify runtimes within the current OS user. A running name cannot be taken over
by another file. Keep the file path and name stable; run `down` before moving or
renaming the deployment. Commands operate on the selected deployment, rather than
discovering every deployment on the machine.

## Deployment version 2

```yaml
version: 2
name: lab-demo
server:
  bind: 127.0.0.1
  port: 5020
devices:
  - id: adam-5017uh
    model: examples/models/products/advantech/adam-5017uh/model.tm.json
    parameters:
      THING_ID: urn:modsim:example:adam-5017uh
      UNIT_ID: 1
    data: examples/models/products/advantech/adam-5017uh/model.sim.json
```

`devices` may be empty. IDs and deployment names use lowercase letters, digits
and hyphens, starting with a letter or digit (maximum 64 characters). Device IDs,
instantiated TD IDs and Unit IDs must each be unique within the deployment.
Paths in the repository example resolve from the project root; for standalone
deployments, model, data and script paths resolve relative to the deployment file.
Models may also use bounded HTTPS URLs. Pin remote model revisions
for repeatable runs.

Each device contains only `id`, `model`, and optional `parameters`, `data`,
`script` and `scriptParameters` (values a script reads as `device.parameters`). A model must be a profile 0.2 TM. Its instantiated TD must have a
stable URI `id`. Supply `THING_ID` when the TM declares that placeholder or has no `id`.
The deployment device ID selects management operations; the TD ID identifies the
Thing; Unit ID selects the device in Modbus requests. A device's TD ID cannot
change during an update: remove it in one successful `up`, then recreate it.

`parameters` supplies typed TM bindings through the published shared interpreter:

* `HOST`, `PORT` and `UNIT_ID` are reserved instance arguments, passed to the
  interpreter's host, port and unit-id API. They can also satisfy its corresponding
  reserved placeholders. `AUTHORITY` is derived; use `HOST` and `PORT` instead.
* `THING_ID` supplies an explicit TD identity when the TM has no `id`.
* Other keys must match TM placeholders. Missing or unused bindings are errors.
* HOST and PORT default to the concrete listener bind address and listener port.
  A wildcard bind requires explicit HOST. An advertised endpoint can differ from
  the listener for container port mappings or proxies; no connectivity test or
  port forwarding is performed by export. The deployer must configure that route.
* UNIT_ID defaults to the model declaration, or the interpreter's fallback 1.
  Declare it explicitly when creating multiple instances of an unbound TM.

The deployment format is a Modsim contract, not a standard TD object. TD generation
uses `modpoll-wot==0.2.0a2` and its bundled TD/Modbus/profile validation. There is
no private TD parser or arbitrary TD patch mechanism.

`data` names [simulation data](model-driven-simulation.md#simulation-data) or a modpoll
snapshot. Both JSON and YAML documents are accepted by managed deployments.
There is no duplicate initial-value field in deployment v2. Omitting data
produces valid static initial values from the model. Simulation data is not
exported as TD defaults.

Deployment files must use the `.yaml` or `.yml` extension. YAML uses safe loading with a 1 MiB document limit, bounded nesting and JSON
compatible values; aliases, duplicate keys, implicit dates and non-finite numbers
are rejected. Use quoted strings where YAML scalar inference is inappropriate.

## Update and reset behavior

Before changing a runtime, `up` validates every model and data document and initializes
all new or changed candidates. An invalid candidate leaves the live device set
unchanged. This guarantee covers simulator state, not external side effects in
explicitly enabled Python scripts.

* Unchanged devices retain register writes, elapsed simulation time, random state
  and script state. Repeating `up` does not rerun their initialization hooks.
* New IDs create independent devices. Removed IDs stop their tasks. Removing the
  last device leaves the listener available for a subsequent `up`.
* Changed model, parameters, data or behavior source replaces that device and
  resets its state. Changes are detected by content, not just file paths.
* Listener changes require `down` followed by `up`.

Supported protocol reads/writes and synchronous hooks do not suspend while using
device state. Registry replacement happens without yielding on the same event
loop, keeping an entire write and its echo on one device generation. Other Unit
IDs and established TCP connections remain available during updates.

```bash
modsim reset --device adam-5017uh
modsim logs
```

`reset` rebuilds that device from the last successfully applied input snapshot,
including the original behavior source. It does not read pending file edits.
`logs` prints the last 1 MiB of the deployment log; `logs -f` or `logs --follow` keeps watching.
For `logs`, use `--file examples/deployment.yaml` to select a deployment; `-f` means follow.
`ps` reports device IDs, TD IDs,
Unit IDs, process ID and failure status as JSON.

Local Python execution requires `up --allow-scripts` when starting the process.
Updates cannot grant script permission to a process started without it; restart
with the flag. `--dry-run` validates candidates and checks script syntax without
executing Python behavior. It reports additions, removals, replacements and kept
devices without changing the runtime. Initialization hooks are only exercised
during a real application of the update.

In managed mode, a periodic behavior failure takes that device offline and marks
it failed in `ps`; other devices continue. Repeated unchanged `up` preserves that
failure status. Use `reset` to retry or change the data or script and run `up`. The legacy
flag-based startup retains its existing process-wide failure behavior.

## TD export

```bash
modsim export
modsim export --device adam-5017uh -o output/adam-5017uh.td.json
modsim export --running --device adam-5017uh -o output/applied.td.json
```

By default, `modsim export` writes every TD to `output/` in the project root.
The directory is ignored by Git. `--output-dir` changes the destination.

Offline export reads the deployment, instantiates its TMs and validates the TDs;
it needs no running process or data files and never executes behavior scripts. `--running`
exports the last successfully applied TDs, so pending file edits cannot be
mistaken for the active configuration. TD export describes interfaces and
advertised endpoints, not current register values or a runtime snapshot.

## Compatibility and scope

`modsim --config ...` remains available for single-device operation.
Managed deployments require version `2`; version `"1"` and the former
`--deployment` entry point are no longer supported.
YAML support is an explicit
runtime dependency.

Management uses private per-user Unix sockets and locks under the OS temporary
directory. It exposes no network management listener. Concurrent first starts
cannot acquire the same deployment lock; a losing start reports an error and can
be retried. SIGINT/SIGTERM and `down` close listeners, cancel device tasks and
remove the socket. The lock and log files remain for safe locking and inspection.
No remote API, multi-listener management, fault injection or state migration is
included in this change.

Prepare pinned example inputs from the repository root with
`uv run python tools/fetch-models.py`; see `examples/model-source.yaml`.

## Run with Docker Compose

From the `examples/` directory of the modsim source, build and start the current source:

```bash
docker compose up -d --build
docker compose logs -f
```

Compose publishes Modbus TCP only on host `127.0.0.1:5020` and restarts the container unless stopped. Each
restart resets simulation state. TDs advertise `127.0.0.1` by default; configure the advertised host and port
mapping when clients connect from another machine.

The deployment, model and simulation data files are mounted from the repository. `docker compose up -d` starts
the configured deployment; do not run `modsim up` again just to start it. After editing the mounted deployment
file, apply it to the running simulator with:

```bash
docker compose exec modsim python -m modsim up -f /app/deployment.yaml -d
```

Use the mounted path Compose started (`/app/deployment.yaml`); the control socket rejects any other path. An
unchanged device keeps its state; a changed device is replaced. Listener changes require a container restart.
If you replace the deployment file itself, run `docker compose up -d --force-recreate` to refresh its bind
mount. The Compose file maps the default output directory to the host's `examples/td/`, so this command, run
from `examples/`, writes one `*.td.json` file per running device there:

```bash
docker compose exec modsim python -m modsim export --running
```

Stop the Compose deployment with `docker compose down`.

## Example: read the deployment with modpoll

Export all TDs from the current deployment file; modsim does not need to be running:

```bash
modsim export
```

In another terminal, read the exported TD:

```bash
modpoll --once --interval 0 --tcp 127.0.0.1 --tcp-port 5020 \
  --config ./output/adam-6024.td.json --export ./adam-6024-snapshot.json
```

For the last applied configuration of a Docker Compose deployment, use the Compose export command above and
read `./examples/td/adam-6024.td.json` instead. The TD selects Unit ID 2. On a fresh deployment,
`adam6024_raw` reports `AO0_RAW: 100` and `AI0_RAW: 100`; values may differ if previously written.

### Optional: write through MQTT

Start a temporary local broker and a continuously running modpoll process:

```bash
docker run --rm -d --name modpoll-demo-mqtt -p 127.0.0.1:1883:1883 \
  eclipse-mosquitto:2 mosquitto -c /mosquitto-no-auth.conf
modpoll --interval 0 --rate 1 --tcp 127.0.0.1 --tcp-port 5020 \
  --config ./output/adam-6024.td.json --mqtt-host 127.0.0.1 --mqtt-port 1883
```

After modpoll connects, publish a non-retained write to the topic named for the TD's `title`:

```bash
docker exec modpoll-demo-mqtt mosquitto_pub -h 127.0.0.1 \
  -t modpoll/adam6024_raw/set \
  -m '{"object_type":"holding_register","address":10,"value":432}'
```

Run the one-shot modpoll command again. `AO0_RAW` and the loopback `AI0_RAW` should both read `432`. This
synthetic raw value does not verify the physical device's range or behavior. The example broker has no
authentication and is published only on host loopback; port 1883 must be available.

Stop modpoll with Ctrl+C, stop the broker (`docker stop modpoll-demo-mqtt`), then stop modsim with `modsim down`
or the Compose deployment with `docker compose down`.
