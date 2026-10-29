# Runnable examples

Vendor models, original reference documents and custom behaviors live in
[contrib](../contrib/README.md). These examples are included in the v2 checkout and preview container;
the stable 1.x package does not include the deployment runtime.

## Static device

```bash
poetry run modsim --config contrib/advantech/adam-6024/adam-6024.tm.json --unit-id 1
```

## Dynamic device

```bash
poetry run modsim --config contrib/advantech/adam-5017uh/adam-5017uh-slot-0.tm.json \
  --scenario contrib/advantech/adam-5017uh/temperature.sim.json
```

The sine example generates raw counts; it does not infer a temperature scale.
For a local Python behavior use `scripted.sim.json` and `--allow-scripts`.

## Two Unit IDs on one TCP listener

```bash
poetry run modsim up -f examples/lab.sim.json
```

Unit 1 exposes the ADAM-5017UH raw input mapping. Unit 2 exposes the ADAM-6024
raw I/O mapping with synthetic AO→AI and DO→DI loopback. Paths in `lab.sim.json`
are relative to that file, so invocation works from other working directories.

To reference a remote TM, replace a device's `model` value with a modsim GitHub
raw HTTPS URL. Keep the deployment, scenarios and scripts local. Use a fixed
commit/tag for reproducible models. See [configuration](../docs/model-validation.md).

## Generated TD maintenance

```bash
poetry run python tools/generate-td.py
poetry run python tools/generate-td.py --check
```

TMs are maintained in contrib; generated TDs and manifests remain beside each
source. [Earlier interoperability evidence](verification.md) records raw ADAM
mapping validation, independently of the new multi-device runtime.

## Managed deployment example

From the repository root, run `modsim up -f examples/deployment.yaml -d`.
Two devices share `managed-device.tm.json` and `managed-device.sim.json`, with
different stable TD IDs, titles and Unit IDs supplied in deployment parameters.
Read/write holding register PDU address 10; each device starts at 25 and accepts
values 0–100. Edit the device list and repeat `up` to reconcile it. Stop with
`modsim down -f examples/deployment.yaml`.

Export both TDs with
`modsim export -f examples/deployment.yaml --output-dir /tmp/modsim-td`.
The managed commands require the v2 development source; see the
[contract](../docs/managed-deployments.md).

The root `deployment.yaml` and `docker-compose.yaml` provide the corresponding
Docker-managed example. See [Docker Compose instructions](../README.md#docker-compose-managed-deployment).
