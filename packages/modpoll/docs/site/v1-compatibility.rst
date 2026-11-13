v1 compatibility and M3 acceptance
===================================

The v2 change adds the executable TM/TD profile alongside the retained v1 CSV
loader. ``--config`` is the single configuration argument and detects the
format from the content. The
existing transport, decoder, output and raw write paths remain. This table
compares the pinned v1 baseline ``0b42099`` with the v2 implementation; it is
not a claim that all WoT documents or every operating system has been
validated.

.. list-table:: Capability and evidence
   :header-rows: 1
   :widths: 24 38 38

   * - Capability
     - v2 disposition
     - Evidence / limit
   * - Existing CLI
     - Existing transport, rate, interval, output and MQTT arguments retained;
       ``--unit-id`` adds an explicit override. v1 CSV configurations load
       through the same ``--config`` argument, detected from the content.
     - ``test_framer_validation.py``, ``test_csv_config.py`` and existing CLI
       tests. No automatic connection from TM Forms is introduced; a concrete
       TD still supplies its endpoint.
   * - Multiple devices/configurations
     - One Thing per file; split an old multi-device CSV into several JSON files.
       Per-file Unit IDs and unique titles are retained.
     - ``test_modbus_task.py`` and ``test_wot_reading_interop.py``. An invalid file
       is closed while other valid files continue, matching the existing policy.
   * - Poll blocks, gaps and addressing
     - Ordered groups, literal PDU addresses, quantities and gaps preserved.
     - ``verify_modsim_equivalence.py`` compares exact requests and 37 values.
   * - Numeric/register bit/string types
     - Register integer/float widths, bit selectors, odd strings, units and
       multipliers retained; unscaled large integers remain Python integers.
     - Independent struct vectors in all four byte/word orders. Multiplied values
       still use the existing floating-point execution semantics.
   * - Value rendering
     - The console table, the MQTT payload and the JSON snapshot show one number
       for one reading. ``--precision auto`` keeps the precision the source data
       carries; ``--precision N`` rounds every float to at most ``N`` decimals.
     - Intentional change: v1 rounded console and MQTT values to three decimals
       but wrote raw floats to the export, so one reading had two renderings and
       a scaled value of ``0.0001`` read as ``0.0``. Cross-version comparisons
       now compare values rather than bytes.
   * - Numeric/string references in bit tables
     - Restored for complete payload bytes. Offsets remain eight-bit groups;
       numeric width counts bytes, stringN counts N bytes.
     - ``test_m3_compatibility.py`` and actual v1/TM numeric-bit parity tests.
       Incomplete numeric/string spans now fail validation, rather than decoding
       protocol padding or failing later. As in v1, bit-table numeric assembly
       reverses bit order within a byte; word order is not applied to bit tables.
   * - Aliases and overlapping views
     - Distinct property names can decode the same address; every alias is kept.
       Duplicate property membership is still rejected.
     - v1 could silently omit same-address aliases. This is an intentional fix;
       ``test_aliases_decode_every_property_from_one_read`` checks both views
       from one physical request.
   * - Read/write metadata
     - Readable properties are decoded; writeOnly properties are omitted from
       telemetry and remain null in snapshots. Declared blocks still get read.
     - DI/IR are read-only. Raw MQTT address writes do not inherit property-level
       authorization or engineering-value inverse transforms.
   * - UDP
     - Existing socket transport retained; explicit socket framer fixed.
     - Real simulator comparison of v1 CSV and the unbound 0.2 TM output.
   * - Serial RTU / ASCII
     - Serial and ``--rtu`` alias retained, explicit framer uses the actual
       PyModbus enum API instead of rejected class arguments.
     - POSIX PTY tests use the unbound 0.2 TM and verify full outputs and
       independently computed CRC/LRC request bytes. Default RTU matches v1.
       The pinned v1 explicit ASCII path
       fails construction, so ASCII is checked against independent wire/data
       expectations rather than claiming false v1 equivalence.
   * - MQTT protocol/output/commands
     - 3.1.1 and 5.0, grouped JSON, individual topics, diagnostics and existing
       FC5/6/16 commands retained.
     - Private-broker CSV/TM/TD matrix for QoS0/1; TLS/QoS2 CLI tests cover both
       protocols, both output styles, and command readback.
   * - MQTT TLS / authentication
     - Existing TLS version, CA, credentials and explicit insecure option retained.
     - Disposable CA/server certificates verify trusted success, unknown CA,
       hostname mismatch and bad-password refusal. Insecure bypass is explicit.
   * - Failures, counts and snapshots
     - Short responses invalidate missing values; connect/transport failures count
       once per active group. Disabled autoremove groups do not add attempts.
     - Real stop/restart and short-response cases. Invalid values are omitted from
       MQTT and null in atomic JSON snapshots; existing fsync/replace failure
       tests remain.
   * - One-shot exit status
     - A failed group or JSON export makes ``--once`` exit nonzero after cleanup.
     - Intentional correction: v1 could report exit 0 despite failed sampling or
       export. Signal-driven shutdown remains graceful.
   * - MQTT shutdown / outbound queue
     - Accepted publications get a bounded flush window (default five seconds),
       then disconnect precedes joining the network loop. Outstanding messages
       are reported; the outgoing queue is bounded to 1000 entries.
     - A real peer withholding PUBACK verifies shutdown cannot wait indefinitely.
       QoS handshakes do not make raw Modbus writes idempotent.

Current boundaries
------------------

CSV runtime support is retained, so v1 configurations and commands keep
working; new configurations should still prefer profile 0.2 (see
:doc:`csv-migration`). Strings
and bit arrays carrying meaningless numeric scales, invalid rw modes, unknown
types and incomplete payload spans require review rather than silent conversion.
Profile inheritance/templates/actions and new property-based writes are separate
features, not requirements for preserving the old tool.

Automated serial acceptance uses POSIX virtual terminals. On 2026-10-28 the
maintainer also confirmed successful polling of an Eastron meter over physical
RS485. This manual result covers that tested setup; Windows/macOS serial hardware
and other device setups retain their own validation scope. The automated CI
matrix remains Python 3.10–3.12 on Linux.

The functional preview ``2.0.0a1`` and independent ``modpoll-wot==0.1.0a1`` are
published. Application dependencies use the exact registry version; wheel/sdist,
Docker and registry-installed acceptance have passed. See the `validation record <https://github.com/top-maker/modpoll/blob/v2/docs/validation.rst>`_ for release and hardware evidence.
