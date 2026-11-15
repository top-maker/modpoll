# Read a device

modpoll reads the device that a Thing Model describes. `--config` takes a local TM/TD file, an HTTPS URL or a
`modiohub:<id>@<version>` Workspace reference; see [configuration](../reference/modpoll/configuration.md). Each
model describes one device; pass several `--config` paths for several devices. All options are listed in the
[command-line reference](../reference/modpoll/cli.md).

## Examples

Connect to a Modbus TCP device:

```bash
modpoll --tcp 192.168.1.10 --config examples/modsim.tm.json
```

Connect to a Modbus serial device:

```bash
modpoll --serial /dev/ttyUSB0 --serial-baud 9600 --config examples/modsim.tm.json
```

Connect to a Modbus TCP device and publish the data to a remote MQTT broker:

```bash
modpoll --tcp 192.168.1.10 --config examples/modsim.tm.json --mqtt-host broker.emqx.io
```

Connect to a Modbus TCP device and export a local JSON snapshot:

```bash
modpoll --tcp 127.0.0.1 --tcp-port 5020 --config examples/modsim.tm.json --export data.json
```

Replay an exported snapshot with modsim on this computer. A snapshot is
[simulation data](../reference/modpoll-wot/profile.md#simulation-data) as it stands; points that were not read
keep their defaults. It holds readings of a real device, so keep it local:

```bash
modpoll --once --tcp 192.168.1.10 --config examples/modsim.tm.json --export snapshot.json
modsim --config examples/modsim.tm.json --port 5020 --data snapshot.json
```

## Value rendering

The terminal table, the MQTT payload and the JSON snapshot show one number for one reading. The default
`--precision auto` keeps the precision the source data carries:

- A register value with a `modpoll:multiplier` is shown as its exact decimal, so `2301` scaled by `0.1` reads
  `230.1` rather than `230.10000000000002`.
- A `float16` or `float32` register is shown as the shortest decimal that reads back as the same value at that
  width, so `12.34` stays `12.34`.
- A `float64` register keeps its full value.
- Integers, booleans and strings are shown unchanged.

An explicit `--precision N` rounds every float to at most `N` decimals:

```bash
modpoll --tcp 192.168.1.10 --config examples/modsim.tm.json --precision 2
```

Rounding a scaled reading can change the raw register value it names. The exported snapshot doubles as modsim
simulation data, so modpoll logs a warning when that happens. The value is still written as asked for.

## Framers and transports

- Serial (`--serial`, alias `--rtu`) supports the framers `rtu` and `ascii` (for example
  `--serial ... --framer ascii`). With `--framer default`, pymodbus uses RTU. The binary framer was removed in
  pymodbus 3.9. pyserial URLs such as `socket://host:port` and `rfc2217://host:port` work for serial-over-TCP
  tunnels.
- TCP and UDP (`--tcp`, `--udp`) use the `socket` framer; other framers are rejected.

## MQTT data and writes

The default topics use the model's `title`: `modpoll/<title>/data` for samples and `modpoll/<title>/set` for
write commands. The publish, subscribe and diagnostics topic patterns are configurable.

Writes use literal Modbus PDU addresses and raw values. Holding-register arrays use FC16 and must contain 1–123
unsigned 16-bit values within the address range. Malformed payloads, invalid or oversized values, ambiguous
device names and retained messages are ignored and logged. Brokers can clear the retained flag on live
forwarding, so configure the broker not to retain messages on the set topic; QoS does not make a write exactly
once.

Points that fail in a poll cycle are omitted from the MQTT output and written as `null` in the JSON snapshot.
Snapshots from several configuration files are combined and replaced atomically. With `--timestamp`, the
timestamp is the start of the poll cycle in Unix seconds; a device with a point named `timestamp` cannot use it.
