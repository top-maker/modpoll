# Examples

- `modsim.tm.json`: the canonical 0.2 Thing Model used by CLI examples; four
  explicit blocks and 37 properties.
- `modsim.generated.td.json`: its generated local TCP instance for the same
  blocks and properties.
- `modsim.csv`: v1 migration and compatibility-test input. v2 does not load it.

From the repository root, run the self-contained TCP/MQTT demonstration:

```sh
docker compose up --build
# In another terminal:
docker compose exec mosquitto mosquitto_sub -t 'modpoll/#' -C 1
# Stop and remove this demonstration:
docker compose down
```

Compose builds the current modpoll checkout, mounts its TM, and starts a local
modsim and disposable anonymous Mosquitto. Host ports 5020 and 18883 bind only to
loopback. The broker configuration is in `docker/mosquitto.conf`; it is for local
demonstration only. Use an authenticated broker for a deployed application.

The previous separate remote/local Compose examples and CSV template were
removed from v2. Existing 1.x examples remain on `main`; see the
[CSV migration guide](../docs/site/csv-migration.rst) for upgrading a configuration.
