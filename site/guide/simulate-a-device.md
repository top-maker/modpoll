# Simulate a device

modsim runs simulated Modbus devices for development and integration testing. It reads profile 0.2 TM/TD input
and [simulation data](../reference/modpoll-wot/profile.md#simulation-data), and runs independent devices on one
Modbus TCP listener. Models, simulation data, the simulator and the client stay separate. Simulation is not
evidence of physical device behavior.

## One device

```bash
modsim --config device.tm.json --port 5020 --data device.data.json
```

Without `--port`, modsim listens on 5020, so the first command needs no administrator rights; read it with
`modpoll --tcp 127.0.0.1 --tcp-port 5020`. Linux, and macOS when binding to `127.0.0.1`, reserve ports below
1024 for administrators: to listen on the standard port 502, run the command with sudo (with uvx,
`sudo "$(command -v uvx)" modsim --port 502 ...`). modsim prints the same hint when a port is refused. Windows does
not reserve these ports.

A modpoll `--export` snapshot is simulation data too, so a device read once can be replayed locally. Snapshots
hold readings of a real device; keep them on your computer:

```bash
modpoll --config device.tm.json --tcp 192.168.1.10 --once --export snapshot.json
modsim --config device.tm.json --port 5020 --data snapshot.json
```

See [model-driven simulation](../reference/modsim/model-driven-simulation.md) for the supported profile, codecs,
constraints and behavior scripts.

## Modbus RTU

`--serial pty` simulates a Modbus RTU device without hardware (Linux and macOS). modsim creates a virtual serial
cable, prints the port for the client and the matching modpoll command, and removes it on exit:

```bash
modsim --config device.tm.json --serial pty
# Virtual serial port for the client: /dev/pts/7
# Read it with: modpoll --config device.tm.json --serial /dev/pts/7 --serial-baud 9600
```

Virtual ports ignore baud rate and parity, so `--serial-baud` and `--serial-parity` only shape the printed
command. `--serial-link PATH` adds a fixed symbolic link to the client port. Pass a port name instead of `pty` to
listen on an existing serial port with those settings. Windows has no pseudo-terminals: create a virtual serial
pair with a driver such as com0com, listen on one port with `--serial COM5` and connect the client to the other.
`--serial` and `--port` are mutually exclusive.

The single-device model runtime supports TCP and Modbus RTU.

## Several devices

A managed deployment runs several devices on one listener from a YAML file and updates them while running.
`examples/deployment.yaml` in the modsim source starts two virtual ADAM devices: Unit 1 exposes ADAM-5017UH raw
inputs; Unit 2 exposes ADAM-6024 raw I/O with synthetic AO→AI and DO→DI loopback.

```bash
modsim up -f examples/deployment.yaml -d
modsim ps -f examples/deployment.yaml
modsim down -f examples/deployment.yaml
```

Managed commands require POSIX (Linux, macOS or WSL). See
[managed deployments](../reference/modsim/managed-deployments.md) for the file format, updates, logging, TD export
and Docker Compose.

## Models in your ModioHub Workspace

After `modsim login` (see [signing in](verification-reports.md#sign-in-to-modiohub)),
`--config modiohub:<id>@<version>` simulates one of your custom Thing Models, or a shared one without signing in;
the download is checked against the SHA-256 the server states. Deployment files do not take `modiohub:` models,
so a hosted deployment never carries your login.

```sh
modsim --config modiohub:k3x9f2m7q4a8n5bd@latest --port 5020
```

## Unconfigured demo

`modsim --comm tcp --port 5020` starts the legacy demonstration datastore; all Unit IDs share its four Modbus
tables. TCP and UDP use socket framing; UDP listens on loopback. TLS loads `certificates/pymodbus.crt` and
`certificates/pymodbus.key` from the working directory and does not authenticate clients. Serial supports RTU
and ASCII; physical serial hardware has not been validated by the local regression suite. The CLI rejects a
non-default `--store` and the unsupported `--slaves` and `--context` options.
