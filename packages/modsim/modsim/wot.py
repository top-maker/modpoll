"""Compile shared profile 0.2 models into isolated simulator devices."""

import json
from typing import Any

from modpoll_wot import parse_model, parse_parameters  # type: ignore[import-untyped]
from modpoll_wot.loading import load_document  # type: ignore[import-untyped]
from pymodbus.constants import ExcCodes
from pymodbus.simulator import DataType, SimData, SimDevice

from .sources import model_document

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


def configure(args: Any) -> SimDevice:
    """Compile a device; a TD endpoint never becomes the server bind address."""
    from .runtime import Device

    model = getattr(args, "prepared_model", None)
    if model is None:
        model = parse_model(
            model_document(args.config),
            unit_id=args.unit_id,
            parameters=parse_parameters(args.param),
        )
    if model.profile_version != "0.2" or model.properties_json is None:
        raise ValueError("configured simulation requires profile 0.2")
    schemas = json.loads(model.properties_json)
    overrides: dict[str, Any] = {}
    if args.initial_file:
        overrides = load_document(args.initial_file)
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
    writable: dict[str, dict[int, int]] = {table: {} for table in TABLES}
    protected: dict[str, dict[int, int]] = {table: {} for table in TABLES}
    unreadable: dict[str, set[int]] = {table: set() for table in TABLES}
    writable_cells: dict[str, set[int]] = {table: set() for table in TABLES}
    ranges: dict[str, list[tuple[int, int]]] = {table: [] for table in TABLES}
    for group in model.groups:
        ranges[group.table].append((group.start, group.start + group.quantity))
        for address in range(group.start, group.start + group.quantity):
            cells[group.table].setdefault(
                address, False if group.table in TABLES[:2] else 0
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
            item not in writable_cells[table]
            for item in range(address, address + count)
        ):
            return ExcCodes.ILLEGAL_ADDRESS
        if not writing and any(
            item in unreadable[table] for item in range(address, address + count)
        ):
            return ExcCodes.ILLEGAL_ADDRESS
        return None

    device = Device(model, cells, schemas, access)
    origins = {}
    # Explicit defaults first, so an unconstrained alias can inherit existing
    # register contents rather than inventing a conflicting zero.
    ordered = sorted(
        device.codecs,
        key=lambda n: not (
            n in overrides or any(k in schemas[n] for k in ("const", "default", "enum"))
        ),
    )
    assigned: dict[tuple[str, int], tuple[int, int]] = {}
    for name in ordered:
        codec = device.codecs[name]
        schema = schemas[name]
        if name in overrides or any(
            key in schema for key in ("const", "default", "enum")
        ):
            value = codec.initial(overrides.get(name), name in overrides)
        else:
            try:
                value = codec.decode(device.cells)
                codec.validate(value)
                codec.encode(value)
            except (ValueError, UnicodeError, TypeError):
                value = codec.initial(None, False)
        for offset, (raw, mask) in enumerate(codec.encode(value)):
            key = (codec.table, codec.start + offset)
            previous, owned = assigned.get(key, (0, 0))
            if (previous ^ raw) & owned & mask:
                raise ValueError(f"{name}: conflicting alias initial values")
            assigned[key] = ((previous & ~mask) | (raw & mask), owned | mask)
            if codec.member.writable:
                writable_cells[codec.table].add(key[1])
            permissions = writable if codec.member.writable else protected
            permissions[codec.table][key[1]] = (
                permissions[codec.table].get(key[1], 0) | mask
            )
            if not codec.member.readable:
                unreadable[codec.table].add(key[1])
        device.set_many({name: value}, initializing=True)
        origins[name] = (
            "override"
            if name in overrides
            else next(
                (key for key in ("const", "default", "enum") if key in schema),
                "synthetic type/constraint fallback",
            )
        )
    device.validate_cells(set(assigned))
    for table in TABLES:
        for address, mask in writable[table].items():
            writable[table][address] = mask & ~protected[table].get(address, 0)
    device.write_masks = writable
    args.runtime = device
    args.model_initialization = {
        "title": model.title,
        "profile": model.profile_version,
        "unit_id": model.unit_id,
        "values": {name: device.get(name) for name in device.codecs},
        "origins": origins,
        "groups": [
            {"table": g.table, "start": g.start, "quantity": g.quantity}
            for g in model.groups
        ],
    }
    blocks = []
    for table in TABLES:
        bits = table in TABLES[:2]
        blocks.append(
            [
                SimData(
                    address,
                    values=[value],
                    datatype=DataType.BITS if bits else DataType.REGISTERS,
                    readonly=not writable[table].get(address, 0),
                )
                for address, value in sorted(device.cells[table].items())
            ]
            or [
                SimData(
                    0,
                    values=[False] if bits else 0,
                    datatype=DataType.BITS if bits else DataType.INVALID,
                )
            ]
        )
    return SimDevice(
        model.unit_id, simdata=(blocks[0], blocks[1], blocks[2], blocks[3])
    )
