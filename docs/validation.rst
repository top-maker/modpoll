Configuration replacement verification
======================================

M2 and M3 exercise the complete TM/TD-to-device-to-output path. Tests use a separate
modsim process and compare against the pinned 1.x checkout; no physical device
or contributed device configuration is required.

Reading acceptance
------------------

``tools/verify_modsim_equivalence.py`` compares all 37 simulator properties,
rendered CLI tables, JSON snapshots and the four actual requests from 1.x CSV,
2.x TM and 2.x TD. The local simulator also has independent expected values.
Public remote state may have been changed, so remote runs compare successive
actual snapshots rather than asserting initial values.

The 1.x baseline renders floats with three decimals while 2.x keeps the
precision of the source data, so the cross-version comparison matches values
by magnitude rather than by bytes. Within one version the terminal table, the
MQTT payload and the JSON snapshot are compared exactly, because one
rendering rule produces all three.

``tests/test_wot_reading_interop.py`` independently encodes all supported numeric
register types with Python struct, including integers beyond JavaScript's exact
integer range, and tests all four byte/word orders. It also checks register bits,
odd string lengths, zero/negative/fractional multipliers, Unit ID 7, real local
HTTP model loading, multiple devices, timestamps and JSON precision. A request-recording proxy also
verifies per-model Unit IDs 2 and 7 in one CLI run, with explicit CLI overrides
still available. Invalid
models fail before polling; Modbus exceptions produce null samples without
hiding valid groups.

MQTT acceptance
---------------

``tests/test_mqtt_modsim_interop.py`` runs unmodified 1.x and 2.x CLIs, checking
MQTT 3.1.1 and 5.0, grouped JSON and individual topics, publication topics,
QoS 0/1, diagnostics, retained-command rejection and FC5/6/16 command round trips.
Every run subscribes and publishes only under its own UUID namespace, clears its
retained test key, and directs commands exclusively to a temporary local modsim.

For repeatable acceptance, CI starts a private local Mosquitto broker. The existing
local broker tests additionally cover authentication rejection, subscription
recovery after broker restart and a full receiving queue.

To start an isolated local broker (remove it after testing)::

    printf 'listener 1883\nallow_anonymous true\npersistence false\n' > /tmp/modpoll-mosquitto.conf
    docker run -d --name modpoll-mqtt-acceptance -p 127.0.0.1:18883:1883 -v /tmp/modpoll-mosquitto.conf:/mosquitto/config/mosquitto.conf:ro eclipse-mosquitto:2

Then run with the project uv environment::

    export MODSIM_SOURCE=/path/to/modsim
    export MODSIM_PYTHON=$MODSIM_SOURCE/.venv/bin/python
    export MODPOLL_1X_SOURCE=/path/to/modpoll-1x
    export MODPOLL_MQTT_HOST=127.0.0.1
    export MODPOLL_MQTT_PORT=18883
    uv run pytest -q tests/test_wot_reading_interop.py tests/test_mqtt_modsim_interop.py
    docker rm -f modpoll-mqtt-acceptance

The public broker smoke test can use ``MODPOLL_MQTT_HOST=broker.emqx.io`` and
``MODPOLL_MQTT_PORT=1883`` with ``-k grouped-json``. Both protocol versions passed
that test. In a separate single-topic baseline probe, the 1.x publisher received
65 PUBACKs but the subscriber observed only 15 distinct topics, with no publisher
disconnect recorded. This public-service observation is not treated as a 2.x
regression or hidden by retries: the complete individual-topic matrix is verified
on the isolated broker, where all 1.x/TM/TD messages and values matched.

These tests validate the reading/output contract and existing command paths.
Serial hardware validation and release-ready packaging are separate from these
software acceptance results.

The historical M2 acceptance run on 2026-10-28 passed 109 tests with all
opt-in environments enabled, including the three local authentication/reconnect/queue
tests. Public grouped JSON verification passed four cases: MQTT 3.1.1/5.0 with
QoS 0/1. The six-case local CLI matrix also covered individual-topic output.

M3 compatibility acceptance
---------------------------

The historical M3 acceptance run on 2026-10-28 with Python 3.12.13 passed
**143 tests with no skips**, including the earlier M2 coverage. The separate
CSV/TM/TD equivalence command again matched all 37 values, terminal tables and
four actual block requests. Four TLS tests emitted the existing
``ssl.PROTOCOL_TLSv1_2`` deprecation warning; no certificate failure was ignored.

Additional tests cover UDP, POSIX virtual-serial RTU/ASCII frames with independent
CRC/LRC checks, numeric/string bit-table compatibility, same-address aliases,
short responses, failure statistics, one-shot failure exit status, real device
stop/restart, bounded MQTT shutdown/outgoing queue, and TLS/QoS2 across both MQTT
versions and output modes. See :doc:`v1-compatibility` for intentional fixes and
:doc:`csv-migration` for migration instructions and the reusable AI prompt.

Install serial extras in the development environment and both test fixtures.
With the baseline, simulator and private broker variables above, run::

    export MODPOLL_MQTT_INTEGRATION=1
    uv sync --locked --all-extras --all-groups
    uv run pytest -q tests --junitxml=/tmp/modpoll-acceptance.xml
    uv run python tools/verify_modsim_equivalence.py --modpoll-1x "$MODPOLL_1X_SOURCE" --modsim "$MODSIM_SOURCE" --report /tmp/modpoll-equivalence.json

The TLS tests create temporary certificates using OpenSSL and own an isolated
Docker broker. CI runs the transport and failure tests in its interoperability
job and retains their JUnit report alongside the MQTT/equivalence reports.
Virtual terminals prove framing and software behavior, not RS485 wiring or
physical timing. The automated CI range is Python 3.10 and 3.14 on Linux. The release and manual
hardware results below extend this software evidence.


Published preview and hardware evidence
---------------------------------------

Modpoll 2.0.0a1 pins the published ``modpoll-wot==0.1.0a1`` interpreter. M4 local
acceptance passed 153 tests with no skips. The
`release workflow <https://github.com/top-maker/modpoll/actions/runs/40716440035>`_
then installed the application from PyPI in a directory without application
sources: 18 tests passed with no skips, covering MQTT, commands, TLS and
transports. A separate CSV/TM/TD comparison matched 37 values, terminal tables
and four actual block requests. Both amd64/arm64 images and the versioned Pages
site were published; the stable latest pointers stayed unchanged.

On 2026-10-28 the maintainer reported successful polling of an Eastron meter over
physical RS485. This manual hardware result supplements the automated simulator
and virtual-terminal tests. It is recorded from the maintainer's confirmation;
this cleanup did not rerun that hardware test. It covers the tested Eastron setup,
with other device/platform combinations validated separately. See the Eastron
contributed TD and vendor documents under ``contrib/eastron/``.


Post-preview cleanup verification
---------------------------------

On 2026-10-28 the cleanup retained all 153 automated tests, passing with no skips.
The unified local Compose example was started in an isolated project and delivered
37 valid simulator properties plus a timestamp through MQTT. The obsolete CSV
template and duplicate Compose examples were removed; ``examples/modsim.csv``
remains as the explicit migration-test fixture. See ``examples/README.md`` for
the current runnable example.
