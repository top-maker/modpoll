WoT TM/TD configuration
=======================

The 2.x development branch accepts JSON configurations using WoT TM/TD 1.1.
Use the same ``--config`` argument for either format. A top-level ``@type``
containing ``tm:ThingModel`` (a string or an array entry) selects TM validation;
otherwise the document is validated as TD. File extensions and URL suffixes do
not select the format. An invalid document fails its selected validation; the
loader does not retry it as the other format. This preview supports the fixed
``tm:ThingModel`` spelling, without resolving alternate JSON-LD aliases.

It rejects CSV input. The canonical ``examples/modsim.tm.json`` uses profile
0.2 standard property Forms and explicit acquisition blocks. The generated
``examples/modsim.generated.td.json`` binds that same 37-property model to local
TCP at port 5020. Current development source accepts only profile 0.2; older
profiles must be migrated. Details are in ``packages/modpoll-wot/profile.md``.

Each file describes one device. Its ``title`` is the output device name;
``--unit-id`` overrides the instance Unit ID (range 1–254). Without it, each file
uses the Unit ID declared consistently in its Forms, falling back to 1. Different files
can therefore address different Unit IDs in one process.
Multiple files may be supplied to ``--config``; titles must be unique.
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
* Preserve effective reference names: the old loader replaced spaces with
  underscores. Unknown types or ambiguous fields require review.

The executable contract and test vectors live under
``packages/modpoll-wot``. Strings, bit selectors, four tables and all four
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

The shared package ``0.2.0a1`` introduces profile ``0.2`` with standard Form
mappings and explicit blocks. The application uses the exact published package
version. See
``packages/modpoll-wot/profile.md`` for API details, parameter precedence,
necessary extensions and external Consumer limits. The source example is
``examples/modsim.tm.json``. Generated TDs are instance artifacts.
