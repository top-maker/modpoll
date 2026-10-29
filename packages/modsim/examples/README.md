# Examples

Commands below run from the modsim repository root. Deployment files use YAML;
WoT TM/TD and scenario files retain their own JSON formats.
Both example deployments bind to `0.0.0.0` so they can run inside a container.
When launched directly on the host they accept connections on all interfaces;
change `server.bind` to `127.0.0.1` to restrict local runs. Docker Compose
publishes the port only on the host's loopback interface by default.

## Synthetic devices

Start two independent devices from one TM and scenario:

```bash
poetry run modsim up -f examples/deployment.yaml
```

Each device exposes holding register PDU address 10, initially 25, with valid
values 0–100. Edit the deployment and run `up` again to apply device changes;
`up -d` runs in the background. Stop it with
`poetry run modsim down -f examples/deployment.yaml`.

## ADAM devices

```bash
poetry run modsim up -f examples/deployment-lab.yaml
```

Unit 1 simulates the ADAM-5017UH raw inputs; Unit 2 simulates ADAM-6024 raw I/O
with synthetic AO→AI and DO→DI loopback. The values are not physical-unit
measurements. The deployment uses a wildcard listener for local and container
use, and advertises `127.0.0.1` to clients on the host.

Product TM sources, scenarios, local behavior scripts and reference documents
are in [contrib](../contrib/README.md). Physical device behavior and address
details remain subject to the validation notes for each product.

## Export TDs

```bash
poetry run modsim export -f examples/deployment-lab.yaml --output-dir /tmp/modsim-td
```

For the committed product TDs and their source hashes, run
`poetry run python tools/generate-td.py --check`; omit `--check` to regenerate.
See [verification](verification.md) for the existing synthetic evidence.

## Docker Compose

The repository root contains `docker-compose.yaml`, which uses
`examples/deployment.yaml`. See [Docker Compose instructions](../README.md#docker-compose-managed-deployment)
and [managed deployment commands](../docs/managed-deployments.md).
