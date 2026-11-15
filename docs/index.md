# modpoll, modsim and modpoll-wot

Three tools that read, simulate and describe Modbus devices with W3C WoT Thing Models. Each is released to
PyPI on its own:

- **modpoll** reads Modbus TCP and RTU devices from a Thing Model, publishes readings to MQTT and writes
  verification reports.
- **modsim** simulates a Modbus device from a Thing Model, over TCP or a virtual serial port.
- **modpoll-wot** holds the executable Thing Model profile, fingerprints and report schemas that both tools share.

```{image} images/modpoll-usage.png
:alt: modpoll polls Modbus devices and publishes the readings to an MQTT broker
```

Start with [installation](guide/installation.md) and the [quickstart](guide/quickstart.md). ModioHub accounts,
device authorization and report uploads on the platform side are documented on ModioHub.

```{toctree}
:caption: Guides
:maxdepth: 1
:hidden:

guide/installation
guide/quickstart
guide/read-a-device
guide/simulate-a-device
guide/verification-reports
guide/migrate-from-v1-csv
```

```{toctree}
:caption: modpoll
:maxdepth: 1
:hidden:

reference/modpoll/cli
reference/modpoll/configuration
reference/modpoll/v1-compatibility
reference/modpoll/changelog
```

```{toctree}
:caption: modsim
:maxdepth: 1
:hidden:

reference/modsim/cli
reference/modsim/model-driven-simulation
reference/modsim/managed-deployments
reference/modsim/changelog
```

```{toctree}
:caption: modpoll-wot
:maxdepth: 1
:hidden:

reference/modpoll-wot/cli
reference/modpoll-wot/profile
reference/modpoll-wot/contract
```
