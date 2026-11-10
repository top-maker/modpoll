# Modpoll 2.0.0a4 preview

Modpoll 2.0.0a4 follows the ModioHub glossary: a decoded value is a point.
The terminal table's first column header changes from `Reference` to `Point`,
and warnings, log messages, CLI help and documentation say point. Scripts that
parse the table header need updating. Legacy CSV `ref` rows, JSON and MQTT
payloads are unchanged.

Modpoll 2.0.0a4 still pins modpoll-wot 0.2.0a4, now consumed from its
standalone repository. Audit behavior is unchanged from 2.0.0a3.

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
