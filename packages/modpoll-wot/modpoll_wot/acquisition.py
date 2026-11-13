"""Execution plan types and profile 0.2 member validation."""

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
    byte_order: str | None = None
    physical_bits: bool = False
    bit_count: int | None = None
    scalar: bool = False

    @property
    def width(self):
        return type_width(self.data_type)


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


def validate_member(
    name, prop, dtype, *, entity, bit, multiplier, endian, scalar, count, path
):
    """Validate decoded property semantics directly, without a legacy document."""
    bits = entity in ("Coil", "DiscreteInput")
    if bit is not None and (bits or dtype != "bool"):
        raise AcquisitionError(f"{path}: register bit selector requires register bool")
    for flag in ("readOnly", "writeOnly"):
        if flag in prop and type(prop[flag]) is not bool:
            raise AcquisitionError(f"{path}: invalid {flag}")
    if prop.get("readOnly") and prop.get("writeOnly"):
        raise AcquisitionError(f"{path}: conflicting access flags")
    readable = not prop.get("writeOnly", False)
    writable = not prop.get("readOnly", False)
    if entity in ("DiscreteInput", "InputRegister") and writable:
        raise AcquisitionError(f"{path}: read-only table requires readOnly")
    if multiplier is not None:
        try:
            multiplier = Decimal(str(multiplier))
        except InvalidOperation as exc:
            raise AcquisitionError(f"{path}: invalid multiplier") from exc
        if not multiplier.is_finite() or not math.isfinite(float(multiplier)):
            raise AcquisitionError(f"{path}: non-finite multiplier")
    if not scalar:
        _schema_type(prop, dtype, bit, multiplier, path)
    return Member(
        name,
        0,
        dtype,
        bit,
        multiplier,
        readable,
        writable,
        prop.get("unit"),
        ("BE" if endian[0] else "LE") + "_" + ("BE" if endian[1] else "LE"),
        bits,
        count if bits else None,
        scalar,
    )


def parse_acquisition(document) -> tuple[Group, ...]:
    """Return the groups of a fully validated profile 0.2 document."""
    from .loading import parse_model

    return parse_model(document).groups
