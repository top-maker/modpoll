Basic Usage
===========

.. argparse::
    :ref: modpoll.arg_parser.get_parser
    :prog: modpoll

The `config` option is required.


Commandline Usage
------------------

- Connect to Modbus TCP device

  .. code-block:: shell

    modpoll --tcp 192.168.1.10 --config examples/modsim.tm.json

- Connect to Modbus serial device

  .. code-block:: shell

    modpoll --serial /dev/ttyUSB0 --serial-baud 9600 --config examples/modsim.tm.json

- Connect to Modbus TCP device and publish data to remote MQTT broker

  .. code-block:: shell

    modpoll --tcp 192.168.1.10 --config examples/modsim.tm.json --mqtt-host broker.emqx.io

- Connect to Modbus TCP device and export a local JSON snapshot

  .. code-block:: shell

    modpoll --tcp 127.0.0.1 --tcp-port 5020 --config examples/modsim.tm.json --export data.json

- Replay an exported snapshot with modsim on this computer. A snapshot is
  simulation data as it stands; points that were not read keep their defaults.
  It holds readings of a real device, so keep it local.

  .. code-block:: shell

    modpoll --once --tcp 192.168.1.10 --config examples/modsim.tm.json --export snapshot.json
    modsim --config examples/modsim.tm.json --port 5020 --data snapshot.json

Value rendering
---------------

The terminal table, the MQTT payload and the JSON snapshot show one number for
one reading. The default ``--precision auto`` keeps the precision the source
data carries:

- A register value with a ``modpoll:multiplier`` is shown as its exact
  decimal, so ``2301`` scaled by ``0.1`` reads ``230.1`` rather than
  ``230.10000000000002``.
- A ``float16`` or ``float32`` register is shown as the shortest decimal that
  reads back as the same value at that width, so ``12.34`` stays ``12.34``.
- A ``float64`` register keeps its full value.
- Integers, booleans and strings are shown unchanged.

An explicit ``--precision N`` rounds every float to at most ``N`` decimals:

  .. code-block:: shell

    modpoll --tcp 192.168.1.10 --config examples/modsim.tm.json --precision 2

Rounding a scaled reading can change the raw register value it names. The
exported snapshot doubles as modsim simulation data, so Modpoll logs a warning
when that happens. The value is still written as asked for.

Configuration File
------------------

The configuration file (`--config`) defines the devices, pollers, and points
to be read. It can be a WoT TM/TD JSON file or a v1 CSV file; the format is
detected from the content. Use `--thing-model` or
`--thing-description`/`--td` to assert the JSON document kind explicitly.

For register references (i.e., Holding or Input registers) with a ``dtype`` of ``bool``, you can specify a single bit to be extracted from the 16-bit register. This is done by appending ``:bit`` to the address, where ``bit`` is an integer from 0 to 15.

- ``40110``: Reads the entire 16-bit register at address 40110.
- ``40110:15``: Reads the 16-bit register at address 40110, extracts bit 15, and returns a boolean value.

The bit is extracted from the final 16-bit value after byte/word swapping based on the poller's endianness configuration.

Framers and transports
----------------------

- Serial (`--serial`, alias `--rtu`) supports framers `rtu` and `ascii` (e.g., `--serial ... --framer ascii`). Binary framer was removed in pymodbus 3.9+. If `--framer default` is used, pymodbus defaults to RTU framer.
- TCP/UDP (`--tcp`/`--udp`) use the `socket` framer; other framers are rejected. If `--framer default` is used, pymodbus defaults to socket framer.

MQTT write commands with malformed payloads, invalid values, ambiguous device names, or a retained-message flag are ignored and logged. Register arrays use FC16 and support 1–123 unsigned 16-bit values. Configure the broker not to retain messages on write-command topics; the MQTT retained flag is not guaranteed to remain set during live forwarding.

Points that fail in a poll cycle are omitted from MQTT output and represented as ``null`` in JSON snapshots. Multiple configuration files are combined into one atomically replaced snapshot.
