# Contributing to modpoll-wot

modpoll-wot is developed in the [modpoll repository](https://github.com/top-maker/modpoll/tree/v2) together with
modpoll and modsim, and released with tags `modpoll-wot-v<version>`; see the repository README for the workspace
and the release flow. Releases `0.3.0a1` to `0.6.0a2` came from a separate modpoll-wot repository (now archived);
their history was carried over.

Install [mise](https://mise.jdx.dev/installing-mise.html), then run the source tests, build the wheel and sdist,
and smoke-test the installed wheel:

```sh
mise trust
mise install
mise run check
```

Released versions and tags are immutable. A failed publish never replaces an existing version: rerun the failed
job, or release a new version.
