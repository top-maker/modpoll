# Installation

This site describes the 2.x preview. The three tools need Python 3.10 or later and are installed with
[uv](https://docs.astral.sh/uv/), which keeps each tool in its own environment. The same commands work in
Windows PowerShell.

```bash
uv tool install --prerelease allow "modpoll==2.0.0a14"
uv tool install --prerelease allow "modsim==2.0.0a16"
uv tool install --prerelease allow "modpoll-wot==0.7.0a3"
```

Modbus RTU support (pyserial) is included in modpoll since 2.0.0a12. For existing CSV installations use
`uv tool install 'modpoll<2'` and the [1.x documentation](https://top-maker.github.io/modpoll/1.x/). See
[v1 compatibility](../reference/modpoll/v1-compatibility.md) for tested platforms and hardware limits.

To upgrade within the 2.x line, or to uninstall:

```bash
uv tool install --upgrade --prerelease allow "modpoll<3"
uv tool uninstall modpoll
```

To use modpoll-wot as a library, add it to your project with `uv add --prerelease allow modpoll-wot` (or
`pip install --pre modpoll-wot`). Import from `modpoll_wot` only; its submodules are not a public interface. The
package ships `py.typed`.

## Run with Docker

The preview images run without a local installation and show the tool version by default:

```bash
docker run --rm topmaker/modpoll:2.0.0a14
```

The stable `latest` tag stays on 1.x. To read a local configuration file, mount its folder into the container.
On Linux, host networking connects the container to a simulator on the host; `-d` (daemon mode) suppresses the
tables:

```bash
docker run --rm --network host -v "$(pwd)/examples:/app/examples:ro" topmaker/modpoll:2.0.0a14 \
  modpoll -d --tcp 127.0.0.1 --tcp-port 5020 --config /app/examples/modsim.tm.json
```
