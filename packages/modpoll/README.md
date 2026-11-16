# modpoll

[![Release](https://img.shields.io/github/v/release/top-maker/modpoll)](https://github.com/top-maker/modpoll/releases)
[![License](https://img.shields.io/github/license/top-maker/modpoll)](https://github.com/top-maker/modpoll/blob/v2/packages/modpoll/LICENSE)
[![Downloads](https://static.pepy.tech/badge/modpoll/week)](https://pepy.tech/project/modpoll)

A command-line tool that reads Modbus TCP and RTU devices from a W3C WoT Thing Model, publishes the readings to
MQTT and writes verification reports. v1 CSV configurations keep working.

```bash
uv tool install --prerelease allow "modpoll==2.0.0a15"
modpoll --once --tcp 192.168.1.10 --config device.tm.json
```

Stable 1.x stays available with `uv tool install 'modpoll<2'`.

**Documentation:** [2.x preview](https://top-maker.github.io/modpoll/v2/) ·
[1.x](https://top-maker.github.io/modpoll/1.x/)

The implementation is inspired by [modbus2mqtt](https://github.com/owagner/modbus2mqtt) and
[spicierModbus2mqtt](https://github.com/mbs38/spicierModbus2mqtt) (MIT license); thanks to Oliver Wagner and
Max Brueggemann. For development, see [CONTRIBUTING.md](CONTRIBUTING.md).

MIT © 2021-2026, Ying Shaodong
