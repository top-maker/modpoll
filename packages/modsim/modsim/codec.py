"""Encode/decode the shared profile's wire mappings without reparsing models."""

import math
import struct
from fractions import Fraction
from typing import Any

from jsonschema import Draft7Validator  # type: ignore[import-untyped]

FORMATS = {
    "uint16": "H",
    "int16": "h",
    "uint32": "I",
    "int32": "i",
    "uint64": "Q",
    "int64": "q",
    "float16": "e",
    "float32": "f",
    "float64": "d",
}


class Codec:
    """A property owns a span and masks within that span, not just its first cell."""

    def __init__(self, group: Any, member: Any, schema: dict) -> None:
        self.group, self.member, self.schema = group, member, schema
        self.name, self.table = member.property, group.table
        self.start = group.start + member.offset
        self.bits = member.physical_bits
        self.dtype = member.data_type
        self.span = member.bit_count if self.bits else member.width
        self.order = member.byte_order or group.byte_order
        self.factor = (
            Fraction(str(member.multiplier))
            if member.multiplier is not None
            else Fraction(1)
        )
        self.validator = Draft7Validator(schema)
        if (
            self.dtype not in FORMATS
            and self.dtype not in ("bool", "bool8", "bool16")
            and not self.dtype.startswith("string")
        ):
            raise ValueError(f"{self.name}: unsupported codec {self.dtype}")

    def validate(self, value: Any) -> None:
        if not self.validator.is_valid(value):
            raise ValueError(
                f"{self.name}: value violates model constraints: {value!r}"
            )
        if type(value) is float and not math.isfinite(value):
            raise ValueError(f"{self.name}: non-finite value")

    def ordered(self, payload: bytes) -> bytes:
        # This involution matches the profile 0.2 consumer semantics. Legacy
        # packed bit payloads ignore word order; packed strings ignore both.
        if self.bits and self.dtype.startswith("string"):
            return payload
        chunks = [payload[i : i + 2] for i in range(0, len(payload), 2)]
        if self.order.startswith("LE_"):
            chunks = [chunk[::-1] for chunk in chunks]
        if not self.bits and self.order.endswith("_LE"):
            chunks.reverse()
        return b"".join(chunks)

    def payload(self, cells: Any) -> bytes:
        values = [
            cells[self.table][i] for i in range(self.start, self.start + self.span)
        ]
        if self.bits:
            return bytes(
                sum(bool(bit) << (7 - j) for j, bit in enumerate(values[i : i + 8]))
                for i in range(0, len(values), 8)
            )
        return b"".join(int(value).to_bytes(2, "big") for value in values)

    def decode(self, cells: Any) -> Any:
        member = self.member
        if self.bits and self.dtype == "bool":
            values = [
                bool(cells[self.table][i])
                for i in range(self.start, self.start + self.span)
            ]
            return values[0] if member.scalar else values
        payload = self.payload(cells)
        if member.bit is not None:
            return bool(
                (int.from_bytes(self.ordered(payload), "big") >> member.bit) & 1
            )
        if self.dtype in ("bool", "bool8", "bool16"):
            count = 16 if self.dtype == "bool16" else 8
            return [bool(payload[i // 8] & (1 << (i % 8))) for i in range(count)]
        payload = self.ordered(payload)
        if self.dtype.startswith("string"):
            return payload[: int(self.dtype[6:])].decode("utf-8").rstrip("\0")
        raw = struct.unpack(">" + FORMATS[self.dtype], payload)[0]
        if member.scalar:
            return bool(raw)
        if self.dtype.startswith("float"):
            value = raw * float(self.factor)
            if not math.isfinite(value):
                raise ValueError(f"{self.name}: non-finite decoded value")
            return value
        value = raw * self.factor
        return value.numerator if value.denominator == 1 else float(value)

    def encode(self, value: Any) -> list[tuple[int, int]]:
        """Return (value, owned mask) for each wire cell, preserving other bits."""
        self.validate(value)
        member = self.member
        if self.bits and self.dtype == "bool":
            values = [value] if member.scalar else value
            if (
                not isinstance(values, list)
                or len(values) != self.span
                or any(type(v) is not bool for v in values)
            ):
                raise ValueError(f"{self.name}: expected {self.span} boolean bits")
            return [(int(v), 1) for v in values]
        length = self.span // 8 if self.bits else self.span * 2
        mask = b"\xff" * length
        if member.bit is not None:
            if type(value) is not bool:
                raise ValueError(f"{self.name}: expected boolean")
            mask = self.ordered((1 << member.bit).to_bytes(2, "big"))
            payload = mask if value else b"\0\0"
        elif self.dtype in ("bool", "bool8", "bool16"):
            count = 16 if self.dtype == "bool16" else 8
            if (
                not isinstance(value, list)
                or len(value) != count
                or any(type(v) is not bool for v in value)
            ):
                raise ValueError(f"{self.name}: expected {count} boolean bits")
            payload = bytes(
                sum(int(v) << j for j, v in enumerate(value[i : i + 8]))
                for i in range(0, count, 8)
            ).ljust(length, b"\0")
            mask = (b"\xff" * (count // 8)).ljust(length, b"\0")
        elif self.dtype.startswith("string"):
            capacity = int(self.dtype[6:])
            payload = value.encode("utf-8")
            if len(payload) > capacity or value.endswith("\0"):
                raise ValueError(
                    f"{self.name}: string is not losslessly encodable in {capacity} bytes"
                )
            payload = self.ordered(payload.ljust(length, b"\0"))
        else:
            if member.scalar:
                if type(value) is not bool:
                    raise ValueError(f"{self.name}: expected boolean")
                raw: Any = int(value)
            else:
                if type(value) not in (int, float):
                    raise ValueError(f"{self.name}: expected a finite numeric value")
                if not self.factor:
                    if value != 0:
                        raise ValueError(
                            f"{self.name}: zero multiplier only represents zero"
                        )
                    raw = Fraction(0)
                else:
                    raw = Fraction(str(value)) / self.factor
                if self.dtype.startswith("float"):
                    raw = float(raw)
                elif raw.denominator != 1:
                    raise ValueError(
                        f"{self.name}: value is not an exact integer after inverse multiplier"
                    )
                else:
                    raw = raw.numerator
            try:
                payload = self.ordered(struct.pack(">" + FORMATS[self.dtype], raw))
            except (OverflowError, struct.error) as exc:
                raise ValueError(
                    f"{self.name}: value cannot be encoded as {self.dtype}"
                ) from exc
        if self.bits:
            return [
                (int(bool(payload[i // 8] & (1 << (7 - i % 8)))), 1)
                for i in range(self.span)
            ]
        return [
            (
                int.from_bytes(payload[i : i + 2], "big"),
                int.from_bytes(mask[i : i + 2], "big"),
            )
            for i in range(0, length, 2)
        ]

    def initial(self, supplied: Any, explicit: bool) -> Any:
        if explicit:
            candidates = [supplied]
        elif "const" in self.schema:
            candidates = [self.schema["const"]]
        elif "default" in self.schema:
            candidates = [self.schema["default"]]
        elif "enum" in self.schema:
            candidates = list(self.schema["enum"])
        else:
            candidates = self.fallbacks()
        for value in candidates:
            try:
                encoded = self.encode(value)
                probe = {
                    self.table: {
                        self.start + i: raw for i, (raw, mask) in enumerate(encoded)
                    }
                }
                self.validate(self.decode(probe))
                return value
            except (ValueError, TypeError, UnicodeError):
                pass
        raise ValueError(
            f"{self.name}: no schema-valid encodable initial value; provide an explicit initial value"
        )

    def fallbacks(self) -> list:
        schema = self.schema
        if schema.get("type") == "boolean":
            return [False, True]
        if schema.get("type") == "array":
            count = self.span if self.bits else (16 if self.dtype == "bool16" else 8)
            item = schema.get("items", {})
            preferred = next(
                (v for v in [False, True] if Draft7Validator(item).is_valid(v)), False
            )
            return [[preferred] * count]
        if self.dtype.startswith("string"):
            length = schema.get("minLength", 0)
            capacity = int(self.dtype[6:])
            return ["", "x" * length] if length <= capacity else [""]
        if not self.factor:
            return [0]
        candidates: list = [0]
        # Integer wire types use exact rational interval arithmetic and a raw
        # quantum. This avoids enumeration and float loss at 64-bit boundaries.
        if self.dtype.startswith(("int", "uint")):
            width = int(self.dtype.lstrip("uint"))
            signed = self.dtype.startswith("int")
            low = -(1 << (width - 1)) if signed else 0
            high = (1 << (width - 1)) - 1 if signed else (1 << width) - 1
            for key, lower, exclusive in [
                ("minimum", True, False),
                ("exclusiveMinimum", True, True),
                ("maximum", False, False),
                ("exclusiveMaximum", False, True),
            ]:
                if key not in schema:
                    continue
                bound = Fraction(str(schema[key])) / self.factor
                raw_lower = lower == (self.factor > 0)
                if raw_lower:
                    low = max(
                        low, math.floor(bound) + 1 if exclusive else math.ceil(bound)
                    )
                else:
                    high = min(
                        high, math.ceil(bound) - 1 if exclusive else math.floor(bound)
                    )
            quantum = 1
            if "multipleOf" in schema:
                quantum = abs(
                    (Fraction(str(schema["multipleOf"])) / self.factor).numerator
                )
            for raw in (
                math.ceil(Fraction(low, quantum)) * quantum,
                math.floor(Fraction(high, quantum)) * quantum,
            ):
                if low <= raw <= high:
                    result = raw * self.factor
                    candidates.append(
                        result.numerator if result.denominator == 1 else float(result)
                    )
            return candidates
        for key in ("minimum", "exclusiveMinimum", "maximum", "exclusiveMaximum"):
            if key in schema:
                bound = schema[key]
                candidates.append(bound)
                float_raw = float(Fraction(str(bound)) / self.factor)
                try:
                    packed = struct.pack(">" + FORMATS[self.dtype], float_raw)
                    number = int.from_bytes(packed, "big")
                    neighbors = [number - 1, number + 1]
                    if float_raw == 0:
                        neighbors.extend([1, (1 << (8 * len(packed) - 1)) | 1])
                    for neighbor in neighbors:
                        if 0 <= neighbor < 1 << (8 * len(packed)):
                            adjusted = struct.unpack(
                                ">" + FORMATS[self.dtype],
                                neighbor.to_bytes(len(packed), "big"),
                            )[0] * float(self.factor)
                            if math.isfinite(adjusted):
                                candidates.append(adjusted)
                except (OverflowError, struct.error):
                    pass
        if "multipleOf" in schema:
            step = Fraction(str(schema["multipleOf"]))
            candidates.extend([float(step), -float(step)])
            for key in ("minimum", "exclusiveMinimum", "maximum", "exclusiveMaximum"):
                if key not in schema:
                    continue
                ratio = Fraction(str(schema[key])) / step
                if key in ("minimum", "exclusiveMinimum"):
                    number = (
                        math.floor(ratio) + 1
                        if key == "exclusiveMinimum"
                        else math.ceil(ratio)
                    )
                else:
                    number = (
                        math.ceil(ratio) - 1
                        if key == "exclusiveMaximum"
                        else math.floor(ratio)
                    )
                candidates.append(float(number * step))
        return candidates
