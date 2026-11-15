# Configuration

modpoll accepts JSON configurations using WoT TM/TD 1.1 and the v1 CSV format. `-f`/`--config` takes either
format and detects it from the content, not the file name or URL suffix: a first non-whitespace byte of `{` or
`[` selects JSON; anything else is parsed as v1 CSV. The same argument also accepts a
`modiohub:<id>@<version>` reference to a custom Thing Model in your ModioHub Workspace (run `modpoll login` first
unless the version is shared); a reference is always a Thing Model. `--config` is the only configuration
argument; there are no format-specific flags.

For JSON input, a top-level `@type` containing `tm:ThingModel` (a string or an array entry) selects TM
validation; otherwise the document is validated as TD. An invalid document fails its selected validation; the
loader does not retry it as the other format. This preview supports the fixed `tm:ThingModel` spelling, without
resolving alternate JSON-LD aliases.

The v1 CSV row format (`device`, `poll` and `ref` rows) keeps its original semantics: point names replace ASCII
spaces with underscores, a blank access column defaults to `r`, the scale column multiplies the decoded value,
and bit-table point addresses identify eight-bit groups. `--unit-id` overrides the per-device ID column;
`--param` placeholder bindings require a Thing Model and are rejected for CSV. The canonical
`examples/modsim.csv` produces the same four blocks and 37 points as `examples/modsim.tm.json`. Only profile 0.2
is accepted; older profiles must be migrated. Details are in the
[modpoll-wot profile](../modpoll-wot/profile.md).

Each file describes one device. Its `title` is the output device name; `--unit-id` overrides the instance Unit
ID (range 1–254). Without it, each file uses the Unit ID declared consistently in its Forms, falling back to 1.
Different files can therefore address different Unit IDs in one process. Several files may be passed to
`--config`; device names must be unique across all files. The transport arguments explicitly select the
connection endpoint. A concrete TD's form Unit IDs, addresses and quantities must agree with the model.

The interpreter validates the official, locally bundled TD/TM 1.1 schema, the project extension schema and
cross-field acquisition semantics. It does not fetch context files or schemas. The local and URL input limit is
1 MiB and the JSON nesting limit is 64. Duplicate JSON keys and non-finite numbers are rejected.

Profile 0.2 places standard types, access flags and units on properties, and standard Modbus Forms carry each
property's raw mapping. `modpoll:acquisition` preserves declared block boundaries, order and holes. Profile 0.1
input is rejected rather than translated or silently accepted. These acquisition semantics are a project
extension, not a W3C standard. The selected subset does not execute arbitrary TD protocol bindings.

The executable contract and its test vectors live in modpoll-wot ([profile](../modpoll-wot/profile.md),
[contract](../modpoll-wot/contract.md)). Strings, bit selectors, four tables and all four byte/word orders are
represented by the contract. Model inheritance, optional members, URI templates, non-Modbus forms and security
schemes other than `nosec` are rejected in this preview subset. The interpreter records access flags; raw MQTT
write commands keep the 1.x behavior and are not property-based writes.

Standard schema validity alone does not establish device correctness or prove that a general WoT consumer will
implement the project's acquisition and transform extensions. See
[v1 compatibility](v1-compatibility.md) for intentional fixes and
[migrating from v1 CSV](../../guide/migrate-from-v1-csv.md) for the conversion procedure.

## Standard Form profile 0.2

The shared modpoll-wot package provides profile 0.2 with standard Form mappings and explicit blocks; modpoll uses
an exact published modpoll-wot version. See the [profile](../modpoll-wot/profile.md) for API details, parameter
precedence, necessary extensions and external consumer limits. The source example is
`examples/modsim.tm.json`, with its generated local TCP instance `examples/modsim.generated.td.json`; both keep
the four original blocks and 37 output references. Generated TDs are instance artifacts.

## Register bits in CSV

For register references (holding or input registers) with a `dtype` of `bool`, a v1 CSV configuration can
extract a single bit from the 16-bit register by appending `:bit` to the address, where `bit` is an integer from
0 to 15:

- `40110` reads the whole 16-bit register at address 40110.
- `40110:15` reads the register at address 40110, extracts bit 15 and returns a boolean.

The bit is extracted from the final 16-bit value, after byte and word swapping by the poller's endianness.
