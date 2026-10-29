"""Optional profile 0.2 raw-I/O adapter for the first model-driven simulator slice.

The shared interpreter owns configuration parsing. This module only initializes
native 16-bit/boolean cells and enforces the declared device's address access.
Install the candidate shared wheel in a validation environment until its registry
release permits the public consumer to pin it normally.
"""

import importlib
import json
import math
from typing import Any

from pymodbus.constants import ExcCodes
from pymodbus.simulator import DataType, SimData, SimDevice


TABLES = ("coil", "discrete_input", "holding_register", "input_register")
FUNCTIONS = {
    1: "coil",
    2: "discrete_input",
    3: "holding_register",
    4: "input_register",
    5: "coil",
    6: "holding_register",
    15: "coil",
    16: "holding_register",
}


def _initial(
    schema: dict[str, Any], dtype: str, supplied: Any, explicit: bool, validator: Any
) -> Any:
    if explicit:
        candidates = [supplied]
    elif "const" in schema:
        candidates = [schema["const"]]
    elif "default" in schema:
        candidates = [schema["default"]]
    elif "enum" in schema:
        candidates = list(schema["enum"])
    elif schema.get("type") == "boolean":
        candidates = [False, True]
    else:
        low, high = (-32768, 32767) if dtype == "int16" else (0, 65535)
        if "minimum" in schema:
            low = max(low, math.ceil(schema["minimum"]))
        if "maximum" in schema:
            high = min(high, math.floor(schema["maximum"]))
        if "exclusiveMinimum" in schema:
            low = max(low, math.floor(schema["exclusiveMinimum"]) + 1)
        if "exclusiveMaximum" in schema:
            high = min(high, math.ceil(schema["exclusiveMaximum"]) - 1)
        candidates = [0] + list(range(low, high + 1))
    check = validator(schema)
    for value in candidates:
        encoded = (
            type(value) is bool
            if schema.get("type") == "boolean"
            else type(value) is int
            and (
                (-32768 <= value <= 32767) if dtype == "int16" else 0 <= value <= 65535
            )
        )
        if encoded and check.is_valid(value):
            return value
    raise ValueError(
        "initial value is not schema-valid and encodable; provide --initial NAME=JSON"
    )


def configure(args: Any) -> SimDevice:
    """Compile one configured device; never derive a listener from a TD endpoint."""
    try:
        core = importlib.import_module("modpoll_wot")
        loading = importlib.import_module("modpoll_wot.loading")
        validator = importlib.import_module("jsonschema").Draft7Validator
        parse_parameters = core.parse_parameters
    except (ImportError, AttributeError) as exc:
        raise ValueError(
            "--config requires the modpoll-wot 0.2 candidate wheel; see docs/model-validation.md"
        ) from exc
    model = core.load_model(
        args.config, unit_id=args.unit_id, parameters=parse_parameters(args.param)
    )
    if model.profile_version != "0.2" or model.properties_json is None:
        raise ValueError("this model-driven slice requires profile 0.2")
    schemas = json.loads(model.properties_json)
    overrides: dict[str, Any] = {}
    if args.initial_file:
        overrides = loading.load_document(args.initial_file)
        if not isinstance(overrides, dict):
            raise ValueError("--initial-file must contain a property-name/value object")
    cli_values = parse_parameters(args.initial)
    if overrides.keys() & cli_values.keys():
        raise ValueError("duplicate initial values in --initial and --initial-file")
    overrides.update(cli_values)
    if overrides.keys() - schemas.keys():
        raise ValueError(
            f"unknown initial properties: {sorted(overrides.keys() - schemas.keys())}"
        )
    cells: dict[str, dict[int, int | bool]] = {table: {} for table in TABLES}
    writable: dict[str, dict[int, bool]] = {table: {} for table in TABLES}
    ranges: dict[str, list[tuple[int, int]]] = {table: [] for table in TABLES}
    assigned: set[tuple[str, int]] = set()
    initialized: dict[str, Any] = {}
    origins: dict[str, str] = {}
    for group in model.groups:
        table = group.table
        ranges[table].append((group.start, group.start + group.quantity))
        for address in range(group.start, group.start + group.quantity):
            cells[table].setdefault(address, False if table in TABLES[:2] else 0)
        for member in group.members:
            if (
                not member.readable
                or member.multiplier is not None
                or member.bit is not None
                or member.data_type not in ("uint16", "int16", "bool")
                or (
                    member.physical_bits
                    and not (member.scalar and member.bit_count == 1)
                )
                or (not member.physical_bits and member.data_type == "bool")
            ):
                raise ValueError(
                    f"{member.property}: this raw-I/O slice supports native 16-bit scalars and scalar booleans only"
                )
            schema = schemas[member.property]
            value = _initial(
                schema,
                member.data_type,
                overrides.get(member.property),
                member.property in overrides,
                validator,
            )
            raw: int | bool = value
            if not member.physical_bits:
                raw = int(value) & 65535
                if (member.byte_order or group.byte_order).startswith("LE_"):
                    raw = ((raw & 255) << 8) | (raw >> 8)
            address = group.start + member.offset
            key = (table, address)
            if key in assigned and cells[table][address] != raw:
                raise ValueError(f"{member.property}: conflicting alias initial values")
            cells[table][address] = raw
            writable[table][address] = (
                writable[table].get(address, True) and member.writable
            )
            assigned.add(key)
            initialized[member.property] = value
            origins[member.property] = (
                "override"
                if member.property in overrides
                else (
                    "const"
                    if "const" in schema
                    else (
                        "default"
                        if "default" in schema
                        else (
                            "enum"
                            if "enum" in schema
                            else "synthetic type/constraint fallback"
                        )
                    )
                )
            )
    blocks: list[list[SimData]] = []
    for table in TABLES:
        bits = table in TABLES[:2]
        if not cells[table]:
            # SimDevice requires nonempty lists. The context rejects every access
            # to this unconfigured sentinel, including bit-table padding.
            blocks.append(
                [
                    SimData(
                        0,
                        values=[False] if bits else 0,
                        datatype=DataType.BITS if bits else DataType.INVALID,
                    )
                ]
            )
        else:
            blocks.append(
                [
                    SimData(
                        address,
                        values=[value],
                        datatype=DataType.BITS if bits else DataType.REGISTERS,
                        readonly=not writable[table].get(address, False),
                    )
                    for address, value in sorted(cells[table].items())
                ]
            )

    def access(
        function_code: int, address: int, count: int, writing: bool
    ) -> ExcCodes | None:
        table = FUNCTIONS.get(function_code)
        if table is None:
            return ExcCodes.ILLEGAL_FUNCTION
        if not any(
            start <= address and address + count <= end for start, end in ranges[table]
        ):
            return ExcCodes.ILLEGAL_ADDRESS
        if writing and any(
            not writable[table].get(item, False)
            for item in range(address, address + count)
        ):
            return ExcCodes.ILLEGAL_ADDRESS
        return None

    args.model_access = access
    args.model_initialization = {
        "title": model.title,
        "profile": model.profile_version,
        "unit_id": model.unit_id,
        "values": initialized,
        "origins": origins,
        "groups": [
            {"table": g.table, "start": g.start, "quantity": g.quantity}
            for g in model.groups
        ],
    }
    return SimDevice(
        model.unit_id,
        simdata=(blocks[0], blocks[1], blocks[2], blocks[3]),
    )


class GuardedContext:
    """Validate exact PDU counts before backend bit packing/padding.

    PyModbus's SimDevice action receives rounded word counts for bit requests;
    enforcing the model at the public context boundary preserves physical counts.
    """

    def __init__(self, backend: Any, access: Any) -> None:
        self.backend = backend
        self.access = access

    def device_ids(self) -> list[int]:
        return self.backend.device_ids()  # type: ignore[no-any-return]

    async def async_getValues(
        self, device_id: int, func_code: int, address: int, count: int = 1
    ) -> list[int] | list[bool] | ExcCodes:
        if error := self.access(func_code, address, count, False):
            return error  # type: ignore[no-any-return]
        return await self.backend.async_getValues(device_id, func_code, address, count)  # type: ignore[no-any-return]

    async def async_setValues(
        self,
        device_id: int,
        func_code: int,
        address: int,
        values: list[int] | list[bool],
    ) -> ExcCodes | None:
        if error := self.access(func_code, address, len(values), True):
            return error  # type: ignore[no-any-return]
        return await self.backend.async_setValues(device_id, func_code, address, values)  # type: ignore[no-any-return]
