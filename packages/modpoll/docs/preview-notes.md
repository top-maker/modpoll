# Modpoll 2.0.0a12 preview

Modpoll 2.0.0a12 pins modpoll-wot 0.7.0a1:

- Modbus RTU works without extras: pyserial is now a regular dependency, so `uvx modpoll --rtu ...` and
  `uv tool install modpoll` read serial devices. `modpoll[serial]` still installs, as an empty extra.
- A verification report whose date is not on the calendar (such as `2026-02-31`) is rejected, as ModioHub
  already did on upload.
- modpoll reaches modpoll-wot through its public top-level interface only.

# Modpoll 2.0.0a11 preview

Modpoll 2.0.0a11 pins modpoll-wot 0.6.0a3 and is the first release after modsim and modpoll-wot joined this
repository as one workspace (`packages/`). It changes nothing in modpoll. Release tags are now `modpoll-v<version>`.

# Modpoll 2.0.0a10 preview

Modpoll 2.0.0a10 keeps modpoll-wot 0.6.0a2:

- A one-shot run (`--once`, `--report`) stops at the first group a device does not answer and reports the
  remaining groups as not read, instead of waiting for a timeout on every group.
- Modsim 2.0.0a12 listens on port 5020 by default: read a local simulator with `--tcp 127.0.0.1 --tcp-port 5020`.
  It can also simulate Modbus RTU on a virtual serial port (`modsim --serial pty`), which prints the
  `modpoll --serial ...` command to read it.

# Modpoll 2.0.0a9 preview

`--report` includes the upload and `--upload` stands alone (modpoll-wot 0.6.0a2):

- Bare `--report` asks where to save, whether the values look right, and whether to upload. `--report --yes`
  is the whole non-interactive run: every point read once, the report kept under the default
  `report-<date>.json`, then uploaded — an existing sign-in is required, because `--yes` does not answer the
  browser sign-in (without one the run fails fast instead of hanging).
- `modpoll --upload FILE` uploads a report saved earlier without reading a device: the report is shown
  for confirmation and uploaded once you agree. Bare `--upload` offers the newest `report-*.json` in the
  current directory (`--yes` answers the questions; without a terminal, name the file).
- After you agree, the tool tells you which ModioHub it is signed in to and uploads; the browser sign-in
  starts only when no login exists. Without `MODIOHUB_URL`, the server of the only stored login stands,
  so a login made against staging is no longer mistaken for the default server.

# Modpoll 2.0.0a8 preview

The verification flags move back onto the normal read and the report drops the
product (modpoll-wot 0.6.0a1, report schema 4):

- `--report` on a normal read verifies a Thing Model on real hardware: every point read once, read-only and
  without retries; the verification report (schema 4) holds no address, Unit ID, serial number or value.
  Bare `--report` asks where to save, whether the values look right, and whether to upload.
- `--upload` shows the report and uploads it after you confirm (`--yes` skips the questions); without a
  login the browser sign-in flow starts inline.
- The `verify` subcommand and `--product` are gone: ModioHub resolves the product from the model
  fingerprint (identical for a Thing Model, its Thing Description exports and unmodified forks).

## Modpoll 2.0.0a7 preview

Modpoll 2.0.0a7 pins modpoll-wot 0.5.0a1 and connects to ModioHub:

- `--device <manufacturer>/<model>[@commit]` reads the baseline Thing Model of a catalog product.
- `--full-read` reads every point once, read-only and without retries; `--report FILE` writes the
  verification report (schema 3), which holds no address, Unit ID, serial number or value.
- `modpoll login` signs in with your browser and `modpoll logout` forgets the login. The 7-day tool session
  is kept in `~/.config/modiohub/credentials.json` and is shared with modsim 2.0.0a9.
- `--tm modiohub:<id>@<version>` reads a custom Thing Model from your ModioHub Workspace, and `--upload` shows
  the report of a full read and uploads it after you confirm.

## Modpoll 2.0.0a6 preview

Modpoll 2.0.0a6 pins modpoll-wot 0.4.0a1, which defines simulation data. A
`--export` snapshot is simulation data as it stands, so modsim 2.0.0a8 can
replay a device read once, on your computer:

```sh
modpoll --once --config device.tm.json --tcp DEVICE_HOST --export snapshot.json
modsim --config device.tm.json --data snapshot.json
```

The snapshot format is unchanged. Snapshots hold readings of a real device;
keep them on your computer. With `--export` and `--timestamp`, a device that
has a point named `timestamp` now stops modpoll at startup instead of having
that point overwritten. The bundled `modpoll-wot validate --kind data` checks
a snapshot or a data document. Verification report schema 3 replaces schema 2.

## Modpoll 2.0.0a5 preview

Modpoll 2.0.0a5 removes `--audit` and pins modpoll-wot 0.3.0a3, which removes
the `modpoll:audit` plan. Thing Models are fully open, and a full read executes
the whole `modpoll:acquisition` plan, so TM authors only write acquisition
groups. A TM that still declares `modpoll:audit` is rejected as an unsupported
root project extension; delete the key. Read a device once with:

```sh
modpoll --once --config device.tm.json --tcp DEVICE_HOST --unit-id 1
```

Verification report generation over a full read is planned separately.

## Modpoll 2.0.0a4 preview

Modpoll 2.0.0a4 follows the ModioHub glossary: a decoded value is a point.
The terminal table's first column header changes from `Reference` to `Point`,
and warnings, log messages, CLI help and documentation say point. Scripts that
parse the table header need updating. Legacy CSV `ref` rows, JSON and MQTT
payloads are unchanged.

Modpoll 2.0.0a4 pins modpoll-wot 0.3.0a2, now released from its standalone
repository. The bundled `modpoll-wot` command adds `fingerprint`, which prints
model and point fingerprints, and `validate-report`, which checks a hardware
verification report. Model loading and audit behavior are unchanged from
2.0.0a3; `--audit` still needs a TM with a `modpoll:audit` plan.

## Modpoll 2.0.0a3 preview

Container users can select `topmaker/modpoll:2.0.0a3-r1` for the packaging
correction. It runs the same application version.

### Local audit

Modpoll 2.0.0a3 pins modpoll-wot 0.2.0a4. Run a single read-only sampling pass:

```sh
modpoll --audit --config device.audit.tm.json --tcp DEVICE_HOST --unit-id 1
modpoll --audit --config device.audit.tm.json --serial SERIAL_PORT --serial-baud 9600 --unit-id 1
```

Install the serial extra for RTU. Use the device's actual serial settings and
Unit ID. Audit reads at most 16 selected properties, with no Modbus retries
and at most five seconds of response timeout per point. Its JSON report
separates identity and status, preserves per-point results, and exits nonzero
on failure. A successful identity sample reports device values for inspection.
A malformed plan is rejected before contacting the device.

### Previous preview

Published shared interpreter 0.2.0a3 and current development source execute only
profile 0.2 and reject profile 0.1. The application release snapshot below keeps
its original dependencies and behavior; publishing the shared schema does not
republish the application.

Modpoll 2.0.0a2 is a functional preview using WoT TM/TD 1.1 profile 0.2 as its canonical configuration model. Existing polling blocks, CLI/JSON/MQTT output and raw address commands are retained. No platform service or device library is required.

Install explicitly: `uv tool install --prerelease allow "modpoll[serial]==2.0.0a2"`. The immutable published application pins `modpoll-wot==0.2.0a1`; the current
development manifest pins a2. Do not infer published dependencies from the working tree. Docker: `topmaker/modpoll:2.0.0a2` (amd64/arm64); stable `latest` remains unchanged. Existing CSV users can keep `modpoll<2`.

Documentation: [1.x](https://top-maker.github.io/modpoll/1.x/), [2.x preview](https://top-maker.github.io/modpoll/v2/), [CSV migration and AI prompt](https://top-maker.github.io/modpoll/v2/csv-migration.html), [compatibility matrix](https://top-maker.github.io/modpoll/v2/v1-compatibility.html). Profile 0.2 is a project extension over the W3C draft Modbus vocabulary, not a new W3C standard. That published release also reads profile 0.1; current development source no longer does.

Acceptance includes 37 known simulator properties, exact block requests, independent byte/word vectors, UDP, POSIX virtual RTU/ASCII, MQTT 3.1.1/5.0, QoS0/1/2, TLS, command readback and failure recovery. Release acceptance additionally installs the published package in an environment without application sources.

Intentional fixes include all same-address aliases, short-response validity, failed one-shot exit status and bounded MQTT shutdown. CSV has no runtime fallback; migrate and validate files explicitly. The shared interpreter currently executes no Modbus requests and supports only the documented Modbus subset; no inheritance/actions/general JSON-LD runtime or property-based inverse writes are added.

Tested software matrix: Linux/Python 3.10–3.12. Automated serial tests use virtual terminals; the maintainer additionally confirmed Eastron physical RS485 polling on 2026-10-28. Windows/macOS serial hardware and other setups require their own validation. TLS retains an existing deprecated TLS-version selector. MQTT QoS does not make device writes idempotent; property access flags do not authorize raw MQTT address writes. Check the release workflow result and attached acceptance reports before deployment.
