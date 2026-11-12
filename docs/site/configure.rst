CSV and WoT TM/TD configuration
===============================

The 2.x development branch accepts both the v1 CSV configuration format and
JSON configurations using WoT TM/TD 1.1. ``-f``/``--config`` (alias ``--tm``)
takes either format and detects it from the content, not the file name or URL
suffix: a first
non-whitespace byte of ``{`` or ``[`` selects JSON; anything else is parsed as
v1 CSV. The same argument also accepts a ``modiohub:<id>@<version>`` reference
to a custom Thing Model in your ModioHub Workspace (run ``modpoll login``
first unless the version is shared); a reference is always a Thing Model.
``--thing-model`` and ``--thing-description``/``--td`` assert
the JSON document kind explicitly and reject content of the other kind (or a
CSV file) with a configuration error; they take local paths or URLs only.

For JSON input, a top-level ``@type`` containing ``tm:ThingModel`` (a string or
an array entry) selects TM validation; otherwise the document is validated as
TD. An invalid document fails its selected validation; the loader does not
retry it as the other format. This preview supports the fixed ``tm:ThingModel``
spelling, without resolving alternate JSON-LD aliases.

The v1 CSV row format (``device``, ``poll`` and ``ref`` rows) keeps its original
semantics: point names replace ASCII spaces with underscores, a blank access
column defaults to ``r``, the scale column multiplies the decoded value, and
bit-table point addresses identify eight-bit groups. ``--unit-id`` overrides
the per-device ID column; ``--param`` placeholder bindings require a Thing
Model and are rejected for CSV. The canonical ``examples/modsim.csv`` produces
the same four blocks and 37 points as ``examples/modsim.tm.json``. Current
development source accepts only profile 0.2; older profiles must be migrated.
Details are in the `modpoll-wot profile documentation
<https://github.com/top-maker/modpoll-wot/blob/main/profile.md>`_.

Each file describes one device. Its ``title`` is the output device name;
``--unit-id`` overrides the instance Unit ID (range 1–254). Without it, each file
uses the Unit ID declared consistently in its Forms, falling back to 1. Different files
can therefore address different Unit IDs in one process.
Multiple files may be supplied per flag, and the three flags may be combined;
files load in ``--config``, ``--thing-model``, ``--thing-description`` order.
Device names must be unique across all files.
The existing transport CLI arguments explicitly select the connection endpoint.
A concrete TD's form Unit IDs, addresses and quantities must agree with the model.

The interpreter validates the official, locally bundled TD/TM 1.1 schema,
the project extension schema and cross-field acquisition semantics. It does not
fetch context files or schemas. The local/URL input limit is 1 MiB and the JSON
nesting limit is 64. Duplicate JSON keys and non-finite numbers are rejected.

Profile 0.2 places standard types, access flags and units on properties, and
standard Modbus Forms carry each property's raw mapping. ``modpoll:acquisition``
preserves declared block boundaries, order and holes. Profile 0.1 input is
rejected rather than translated or silently accepted.
These acquisition semantics are a project extension, not a W3C standard. The
selected subset does not execute arbitrary TD protocol bindings.

Migration from CSV
------------------

* Copy the device name to ``title`` and pass its Unit ID through ``--unit-id``.
* Preserve every poll's table, literal start address, quantity and byte/word order.
* Map each property to a Modbus Form with its raw table, literal address,
  quantity, type and byte/word order. List properties in the matching acquisition
  group to preserve the original block boundaries and polling order. Offsets
  are derived from Forms and count physical bits for Coil/DiscreteInput.
* Express read-only and write-only references through ``readOnly`` and
  ``writeOnly``. Neither flag means read/write. DI and IR are read-only tables;
  their historical ``rw`` sample flags must become ``readOnly: true``.
* Copy units unchanged and express the old scale as ``modpoll:multiplier``.
  Multipliers retain the existing floating-point execution behavior; they are
  not interpreted as divisors. Zero and negative multipliers are valid.
* Preserve effective point names from legacy ``ref`` rows: the old loader replaced spaces with
  underscores. Unknown types or ambiguous fields require review.

The executable contract and test vectors live in the
`modpoll-wot repository <https://github.com/top-maker/modpoll-wot>`_. Strings,
bit selectors, four tables and all four
byte/word orders are represented by the contract. Model inheritance, optional members, URI templates, non-Modbus forms,
and security schemes other than ``nosec`` are rejected in this preview subset.
The interpreter records access flags; raw MQTT write commands retain the existing
1.x behavior and are not property-based writes.

Standard schema validity alone does not establish device correctness or prove
that a general WoT consumer will implement the project's acquisition/transform
extensions. This change adds no HTTP/cache service. See :doc:`v1-compatibility` for intentional
fixes and :doc:`csv-migration` for the reusable AI conversion prompt.

Standard Form profile 0.2
-------------------------

The shared ``modpoll-wot`` package provides profile ``0.2`` with standard Form
mappings and explicit blocks. The application uses the exact published package
version. See the
`profile documentation <https://github.com/top-maker/modpoll-wot/blob/main/profile.md>`_
for API details, parameter precedence,
necessary extensions and external Consumer limits. The source example is
``examples/modsim.tm.json``. Generated TDs are instance artifacts.
