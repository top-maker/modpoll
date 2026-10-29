# modsim v2 development source

modsim runs simulated Modbus devices for development and integration testing.
The current source supports profile 0.2 TM/TD input, scenarios and independent
devices on a single managed Modbus TCP listener. The published `2.0.0a1`
preview does not include all current managed commands; see
[preview notes](preview-notes.md).

## Start a managed deployment

From a source checkout, `docker compose up -d --build` runs the root
`examples/deployment.yaml`. Unit 1 is a virtual ADAM-5017UH input module and Unit 2 is a
virtual ADAM-6024 with synthetic I/O loopback. Compose publishes port 5020 on
host loopback. The ADAM mappings are manual-derived candidates; simulation is
not evidence of physical device behavior.

To run locally with Poetry, use `poetry run modsim up`. The default deployment
binds all host interfaces when run directly. See [managed deployments](managed-deployments.md)
for updates, logging, TD export, instance IDs and script permissions.

## Unconfigured demo

`modsim --comm tcp --port 5020` starts the legacy demonstration datastore; all
Unit IDs share its four Modbus tables. TCP and UDP use socket framing; UDP
listens on loopback. TLS uses `certificates/pymodbus.crt` and
`certificates/pymodbus.key` relative to the working directory. It does not
authenticate clients. Serial supports RTU and ASCII; physical serial hardware
has not been validated by the local regression suite.

The CLI rejects non-default `--store` and the unsupported `--slaves` and
`--context` options. Run `modsim --help` for available options.

## More information

- [Model-driven simulation](model-validation.md): TM/TD, codecs and scenarios.
- [Managed deployments](managed-deployments.md): YAML, lifecycle and export.
- [Preview release process](release-process.md): published artifact validation.
- [Modules](modules.md): API reference.
