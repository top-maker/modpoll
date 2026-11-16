# modsim

A Modbus device simulator for integration and testing. It runs a device from a W3C WoT Thing Model and simulation
data, over Modbus TCP or a virtual serial port, and runs several devices on one listener from a deployment file.

```bash
uv tool install --prerelease allow "modsim==2.0.0a17"
modsim --config device.tm.json --port 5020
```

**Documentation:** <https://top-maker.github.io/modpoll/v2/>

For development, see [CONTRIBUTING.md](CONTRIBUTING.md).
