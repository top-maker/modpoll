# ADAM simulation example

The repository root contains the single [deployment.yaml](../deployment.yaml)
and [docker-compose.yaml](../docker-compose.yaml). From the repository root:

```bash
docker compose up -d
docker compose logs -f
docker compose down
```

Unit 1 simulates ADAM-5017UH raw inputs. Unit 2 simulates ADAM-6024 raw I/O
with synthetic AO→AI and DO→DI loopback. These are synthetic raw counts; physical
device mappings, measurement ranges and output limits require hardware validation.
Product models, scenarios and reference documents live in [contrib](../contrib/README.md).

For a local non-Docker run use `poetry run modsim up`. The deployment binds to
`0.0.0.0` for container use, so a direct run listens on all host interfaces;
set `server.bind` to `127.0.0.1` to restrict it. Compose publishes only on host
loopback by default. Export TDs locally using
`poetry run modsim export --output-dir /tmp/modsim-td`.

Run `poetry run python tools/generate-td.py --check` to verify the product TDs
and source hashes. See [managed deployment commands](../docs/managed-deployments.md)
for updates, logs and instance parameters.
