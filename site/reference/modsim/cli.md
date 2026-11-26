# Command line

`modsim` runs one simulated device from flags. The managed commands (`up`, `down`, `ps`, `logs`, `export`,
`reset`) run a [deployment](managed-deployments.md) of several devices on one listener.

```{argparse}
:ref: modsim.utils.get_parser
:prog: modsim
```

## Managed commands

```{argparse}
:ref: modsim.commands.parser
:prog: modsim
```
