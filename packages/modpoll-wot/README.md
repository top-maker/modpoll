# modpoll-wot (experimental)

The executable W3C WoT Thing Model profile that [modpoll](https://pypi.org/project/modpoll/) and
[modsim](https://pypi.org/project/modsim/) share: offline TM/TD validation, TD export, point and model
fingerprints, and the schemas of simulation data and verification reports. It executes no Modbus requests.

```bash
uv add --prerelease allow modpoll-wot      # or: pip install --pre modpoll-wot
uvx --prerelease allow modpoll-wot validate device.tm.json --profile
```

Import from `modpoll_wot` only; its submodules are not a public interface.

**Documentation:** <https://top-maker.github.io/modpoll/v2/> ([profile](profile.md),
[contract](CONTRACT.md)). For development, see [CONTRIBUTING.md](CONTRIBUTING.md).
