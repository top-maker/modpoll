# Quickstart

Use the public Modbus TCP simulator at `modsim.topmaker.net:502` to try modpoll without starting a local server:

```bash
modpoll --once --tcp modsim.topmaker.net --tcp-port 502 --config examples/modsim.tm.json
```

## Run a local simulator

Start a local [modsim](simulate-a-device.md) simulator in one terminal:

```bash
docker run --rm -p 5020:5020 topmaker/modsim:latest
```

In another terminal, poll its sample data once:

```bash
modpoll --once --tcp 127.0.0.1 --tcp-port 5020 --config examples/modsim.tm.json
```

The command assumes you are in the `packages/modpoll` directory of the repository. You can instead provide the
published configuration URL or your own local TM/TD JSON file.

The simulator's default datastore uses literal Modbus addresses:

| Table | Access | Addresses |
| --- | --- | --- |
| Coils | Read/write | 0–31 |
| Discrete inputs | Read-only | 10000–10031 |
| Input registers | Read-only | 30000–30043 |
| Holding registers | Read/write | 40000–40043 |

Coil and discrete input blocks contain 32 bits including padding. All Unit IDs share the default simulator
datastore. See [simulate a device](simulate-a-device.md) for other transports and their limits.
