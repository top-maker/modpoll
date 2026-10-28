"""Version 0.1 acquisition semantics, independent of Modbus transport."""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import re
import math


class AcquisitionError(ValueError):
    """Invalid or unsupported executable configuration."""


ENTITIES = {
    "Coil": "coil",
    "DiscreteInput": "discrete_input",
    "InputRegister": "input_register",
    "HoldingRegister": "holding_register",
}
WIDTHS = {
    "int16": 1,
    "uint16": 1,
    "float16": 1,
    "int32": 2,
    "uint32": 2,
    "float32": 2,
    "int64": 4,
    "uint64": 4,
    "float64": 4,
    "bool": 1,
    "bool8": 1,
    "bool16": 2,
}


@dataclass(frozen=True)
class Member:
    property: str
    offset: int
    data_type: str
    bit: int | None = None
    multiplier: Decimal | None = None
    readable: bool = True
    writable: bool = False
    unit: str | None = None

    @property
    def width(self):
        return type_width(self.data_type)

    @property
    def bit_group_width(self):
        return type_width(self.data_type, bit_table=True)


@dataclass(frozen=True)
class Group:
    table: str
    start: int
    quantity: int
    byte_order: str
    members: tuple[Member, ...]


def type_width(dtype, *, bit_table=False):
    if dtype in WIDTHS:
        width = WIDTHS[dtype]
        return width * 2 if bit_table and not dtype.startswith("bool") else width
    if re.fullmatch(r"string[1-9][0-9]{0,3}", dtype):
        length = int(dtype[6:])
        return length if bit_table else (length + 1) // 2
    raise AcquisitionError(f"unsupported data type: {dtype}")


def _schema_type(prop, dtype, bit, multiplier, path):
    actual = prop.get("type")
    if dtype.startswith("string"):
        valid = actual == "string"
        if multiplier is not None:
            raise AcquisitionError(f"{path}: strings cannot have a multiplier")
    elif dtype.startswith("bool"):
        valid = (
            actual == "boolean"
            if bit is not None
            else (
                actual == "array"
                and isinstance(prop.get("items"), dict)
                and prop["items"].get("type") == "boolean"
            )
        )
        if multiplier is not None:
            raise AcquisitionError(f"{path}: bit values cannot have a multiplier")
    else:
        valid = actual in ("integer", "number")
        if dtype.startswith("float") or (
            multiplier is not None and multiplier != multiplier.to_integral_value()
        ):
            valid = actual == "number"
    if not valid:
        raise AcquisitionError(
            f"{path}: property type disagrees with decoded type/transform"
        )


def parse_acquisition(document) -> tuple[Group, ...]:
    """Apply cross-field checks after structural schema validation."""
    # Also validate here so callers cannot bypass structural validation.
    from .validation import validate_extension

    validate_extension(document)
    properties = document.get("properties", {})
    if not isinstance(properties, dict) or not properties:
        raise AcquisitionError("/properties: expected nonempty object")
    result, seen = [], set()
    for i, group in enumerate(document["modpoll:acquisition"]):
        path = f"/modpoll:acquisition/{i}"
        table = ENTITIES[group["modv:entity"]]
        bits = table in ("coil", "discrete_input")
        start, count = group["modv:address"], group["modv:quantity"]
        if count > (2000 if bits else 125) or start + count > 65536:
            raise AcquisitionError(f"{path}: invalid Modbus range")
        byte_order = (
            ("BE" if group["modv:mostSignificantByte"] else "LE")
            + "_"
            + ("BE" if group["modv:mostSignificantWord"] else "LE")
        )
        members = []
        for j, member in enumerate(group["modpoll:members"]):
            mp = f"{path}/modpoll:members/{j}"
            name = member["modpoll:property"]
            if name not in properties or name in seen:
                raise AcquisitionError(f"{mp}: unknown or duplicate property {name!r}")
            prop = properties[name]
            if not isinstance(prop, dict):
                raise AcquisitionError(f"{mp}: expected property schema")
            dtype, offset = member["modpoll:dataType"], member["modpoll:offset"]
            width = type_width(dtype, bit_table=bits)
            # 1.x bit table references count eight-bit groups, not physical bits.
            limit = (count + 7) // 8 if bits else count
            if offset + width > limit or (
                bits and not dtype.startswith("bool") and (offset + width) * 8 > count
            ):
                raise AcquisitionError(f"{mp}: member outside group")
            bit = member.get("modpoll:bit")
            if bit is not None and (bits or dtype != "bool"):
                raise AcquisitionError(
                    f"{mp}: register bit selector requires register bool"
                )
            for flag in ("readOnly", "writeOnly"):
                if flag in prop and type(prop[flag]) is not bool:
                    raise AcquisitionError(f"{mp}: invalid {flag}")
            if prop.get("readOnly") and prop.get("writeOnly"):
                raise AcquisitionError(f"{mp}: conflicting access flags")
            readable, writable = not prop.get("writeOnly", False), not prop.get(
                "readOnly", False
            )
            if table in ("discrete_input", "input_register") and writable:
                raise AcquisitionError(f"{mp}: read-only table requires readOnly")
            multiplier = None
            if "modpoll:multiplier" in member:
                try:
                    multiplier = Decimal(str(member["modpoll:multiplier"]))
                except InvalidOperation as exc:
                    raise AcquisitionError(f"{mp}: invalid multiplier") from exc
                if not multiplier.is_finite() or not math.isfinite(float(multiplier)):
                    raise AcquisitionError(f"{mp}: non-finite multiplier")
            _schema_type(prop, dtype, bit, multiplier, mp)
            members.append(
                Member(
                    name,
                    offset,
                    dtype,
                    bit,
                    multiplier,
                    readable,
                    writable,
                    prop.get("unit"),
                )
            )
            seen.add(name)
        result.append(Group(table, start, count, byte_order, tuple(members)))
    if seen != properties.keys():
        raise AcquisitionError(
            "/properties: every property must have an acquisition member"
        )
    return tuple(result)
