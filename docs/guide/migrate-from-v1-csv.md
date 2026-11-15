# Migrate from v1 CSV

modpoll 2.x loads v1 CSV configurations: pass them to `--config` as before, and the format is detected from the
content. Existing v1 commands keep working unchanged. Migrating to profile 0.2 is still recommended for new or
heavily edited configurations, because a Thing Model is validated offline, carries access and unit metadata
explicitly, and is what the ModioHub catalog publishes. modpoll does not call an AI service at runtime.

Convert configurations to profile 0.2 as described in the [modpoll-wot profile](../reference/modpoll-wot/profile.md).
Profile 0.1 is rejected; migrate its member mapping into Forms and use physical bit addresses. Check the
executable profile and bundled schemas before using a conversion.

## Field mapping

- Copy the device name to `title` and pass its Unit ID through `--unit-id`.
- Preserve every poll's table, literal start address, quantity and byte/word order.
- Map each property to a Modbus Form with its raw table, literal address, quantity, type and byte/word order.
  List properties in the matching acquisition group to preserve the original block boundaries and polling
  order. Offsets are derived from Forms and count physical bits for Coil/DiscreteInput.
- Express read-only and write-only references through `readOnly` and `writeOnly`. Neither flag means
  read/write. DI and IR are read-only tables; their historical `rw` sample flags must become `readOnly: true`.
- Copy units unchanged and express the old scale as `modpoll:multiplier`. Multipliers keep the existing
  floating-point execution behavior; they are not interpreted as divisors. Zero and negative multipliers are
  valid.
- Preserve effective point names from legacy `ref` rows: the old loader replaced spaces with underscores.
  Unknown types or ambiguous fields require review.

## Procedure

1. Preserve the original CSV and known raw and output samples. Split multiple device sections into separate
   JSON files; give each one its effective device name as `title` and its default Unit ID as root
   `modv:unitID`.
2. Copy every declared block, including holes. JSON addresses are literal PDU integers: convert a hexadecimal
   literal to its numeric value; never subtract 30001/40001 or guess a zero/one-based correction.
3. Translate references into standard property schemas and Modbus Forms. Preserve the effective v1 output key
   (ASCII spaces became underscores), case and punctuation. List each property in the matching
   `modpoll:acquisition` block to preserve request boundaries and poll order.
4. Copy type, unit and scale. `modpoll:multiplier` multiplies the decoded value; it is not a divisor. Zero and
   negative values are valid. A numeric multiplier uses the existing float behavior even if its literal is
   stored as a decimal string. String and bit-group scales that v1 ignored require an explicit review note.
5. Express access with `readOnly` / `writeOnly`; neither means read/write. DI/IR must be readOnly even when an
   old sample says rw. Preserve raw command expectations: these flags do not authorize or block MQTT address
   writes.
6. Validate every output file offline, then compare known vectors and requests. Review the report before using
   the file on a device. A successful schema check alone cannot certify a vendor register map.

```bash
modpoll-wot validate meter.tm.json --profile
modpoll --once --config meter.tm.json --tcp HOST --tcp-port PORT --export data.json
modpoll --config first.tm.json second.tm.json --tcp HOST
```

The last command uses each file's Unit ID unless `--unit-id` is given. Each file creates its own client
connection; connection pooling is not added. A concrete TD's Form Unit IDs must agree with the selected
instance. Prefer an unbound TM when connection information is not supplied; do not invent reachable HTTP or
Modbus endpoints merely to produce a TD.

## Reusable AI prompt

Provide the source CSV, the current [profile](../reference/modpoll-wot/profile.md) and the extension schema
alongside this prompt. The AI may prepare files, but an operator still verifies the result:

```text
Convert the supplied v1 modpoll CSV into the current executable WoT TM 1.1
profile 0.2. Read the supplied profile.md and acquisition schema first. This
task changes configuration format; do not redesign addresses or sampling.

Output:
- One strict JSON *.tm.json file per device, with unique effective titles,
  root modv:unitID, tm:ThingModel type and the exact supported contexts.
- A separate migration report listing every original device, block and ref,
  its new field/property, any corrected access flag, and unresolved issues.
- Equivalent modpoll CLI commands and the exact validation commands/results.
  If you cannot run them, explicitly say "not executed".

Preserve every poll block's order, table, literal start, quantity and holes.
Map coil/discrete_input/input_register/holding_register to the documented
modv:entity terms. Put raw type and literal address/quantity on each Modbus
Form, and list the original polling groups under modpoll:acquisition.
BE_BE/BE_LE/LE_BE/LE_LE map respectively to byte/word flags true/true,
true/false, false/true, false/false.

Preserve each effective ref key: v1 replaced ASCII spaces with underscores;
do not change case, punctuation or hyphens. Preserve every block's order,
start and quantity without converting to per-property polling.
Bit-table offsets count eight-bit groups; register offsets count registers
only when the selected profile uses member offsets.
address:bit is allowed only for a register bool bit 0..15. Strings count bytes.
Numeric/string bit-table members must fit complete requested payload bytes;
do not rely on padded response bits. Preserve the documented legacy bit-table
numeric packing rather than inventing a new byte/word transformation.

Normalize table/type/access tokens to lowercase, as v1 did; a blank access
field defaults to r. Preserve type widths and unit labels. Copy scale as modpoll:multiplier, including
zero, negative and fractional literals. Do not replace multiplication by a
guessed vendor gain/divisor. Use number schemas for float/scaled numeric
output, integer for unscaled integers, string for stringN, boolean for a
selected register bit, and boolean arrays for bool groups.

Translate r/w/rw to the standard property access flags. DI/IR are read-only:
report old rw flags and the correction. Do not claim these flags add raw
MQTT write authorization or inverse engineering-value encoding.

Do not guess unknown types, invalid rw tokens, incomplete rows or duplicate
effective names. Do not silently omit anything to make validation pass.
If a decision is needed, mark the separate report as blocked/needs-review
and explain it; keep reports and unsupported fields out of executable JSON.
A TD is optional only when explicit instance endpoint parameters are supplied;
Forms must agree with the group/member mapping and selected Unit ID.

Check every source ref is accounted for. Run the offline validator, compare
group requests, and compare provided raw/engineering-value vectors. Passing
structural validation is not evidence of real-device correctness.
```

## Review checklist

- Every device and ref is accounted for; duplicate names and aliases are reviewed.
- Table, literal address, count and byte/word flags match the source blocks.
- Offsets and full type spans fit each block; no accidental per-property polling.
- Units, multiplier direction, zero scales and large-integer expectations match.
- Access corrections and rejected source mistakes are explicit in the report.
- All JSON files pass the offline profile validator; independent vectors and output comparisons pass. Unknown
  vendor facts remain unresolved, not guessed.
- No AI calls or device-library dependency are introduced at conversion time.

The authored `examples/modsim.tm.json` / `modsim.generated.td.json` pair and the independent vectors in the tests
demonstrate the process. Migrating the entire `contrib` tree is not a release condition.
