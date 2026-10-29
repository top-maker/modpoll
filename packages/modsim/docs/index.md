# modsim

Modsim is a Modbus simulator for local development and integration with
[modpoll](https://github.com/top-maker/modpoll). Its default datastore contains
coils, discrete inputs, holding registers and input registers. All Unit IDs
share that datastore. A public Modbus TCP simulator is available at
`modsim.topmaker.net:502` for quick testing.

## Run the default simulator

```bash
pip install modsim
modsim --comm tcp --port 5020
```

Alternatively, start the published container:

```bash
docker run --rm -p 5020:5020 topmaker/modsim:latest
```

The default TCP listener uses port 5020. Coils and holding registers are
writable; discrete inputs and input registers are read-only. Unsupported
addresses return a Modbus exception.

## Transports and options

TCP and UDP use socket framing; UDP listens on loopback. TLS uses TLS framing
and expects `certificates/pymodbus.crt` and `pymodbus.key` relative
to the working directory. The TLS server does not authenticate clients. Serial
supports RTU and ASCII framing; physical serial devices have not been
validated in the local regression suite.

Only the sequential datastore is implemented. The CLI rejects non-default
`--store` values and the unsupported `--slaves` and `--context` options. Run
`modsim --help` for the full option list.

The local TCP, UDP and temporary-certificate TLS tests cover startup, reads and
shutdown. SIGINT and SIGTERM handling on Windows has not been verified.
