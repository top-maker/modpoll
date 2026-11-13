"""Compatibility layer for PyModbus API changes.

This module provides backward-compatible wrappers for APIs that changed
between PyModbus 3.6.9 and 3.16.1.
"""

import struct
from typing import List


class Endian:
    """Compatibility class for endianness constants removed in PyModbus 3.16.1."""

    BIG = "big"
    LITTLE = "little"


class BinaryPayloadBuilder:
    """Compatibility wrapper for PyModbus BinaryPayloadBuilder.

    This class was removed in PyModbus 3.9.0+ but is needed for backward
    compatibility with existing datastore initialization code.
    """

    def __init__(self, byteorder: str = "big", wordorder: str = "big") -> None:
        """Initialize the builder.

        Args:
            byteorder: Either "big" or "little" for byte order
            wordorder: Either "big" or "little" for word order (register order)
        """
        self.byteorder = byteorder
        self.wordorder = wordorder
        self._bits: List[bool] = []
        self._registers: List[int] = []

    def add_bits(self, bits: List[bool]) -> "BinaryPayloadBuilder":
        """Add a list of bits to the payload.

        Args:
            bits: List of boolean values

        Returns:
            Self for chaining
        """
        self._bits.extend(bits)
        return self

    def add_16bit_uint(self, value: int) -> "BinaryPayloadBuilder":
        """Add a 16-bit unsigned integer."""
        self._registers.append(value & 0xFFFF)
        return self

    def add_16bit_int(self, value: int) -> "BinaryPayloadBuilder":
        """Add a 16-bit signed integer."""
        # Convert negative to unsigned representation (two's complement)
        if value < 0:
            value = (1 << 16) + value
        self._registers.append(value & 0xFFFF)
        return self

    def add_32bit_uint(self, value: int) -> "BinaryPayloadBuilder":
        """Add a 32-bit unsigned integer (uses 2 registers)."""
        if self.wordorder == "big":
            self._registers.append((value >> 16) & 0xFFFF)
            self._registers.append(value & 0xFFFF)
        else:
            self._registers.append(value & 0xFFFF)
            self._registers.append((value >> 16) & 0xFFFF)
        return self

    def add_32bit_int(self, value: int) -> "BinaryPayloadBuilder":
        """Add a 32-bit signed integer (uses 2 registers)."""
        # Convert to unsigned if negative
        if value < 0:
            value = (1 << 32) + value
        return self.add_32bit_uint(value)

    def add_32bit_float(self, value: float) -> "BinaryPayloadBuilder":
        """Add a 32-bit float (uses 2 registers)."""
        fmt = ">f"  # big-endian float
        packed = struct.pack(fmt, value)
        value_int = struct.unpack(">I", packed)[0]
        return self.add_32bit_uint(value_int)

    def add_64bit_uint(self, value: int) -> "BinaryPayloadBuilder":
        """Add a 64-bit unsigned integer (uses 4 registers)."""
        if self.wordorder == "big":
            self._registers.append((value >> 48) & 0xFFFF)
            self._registers.append((value >> 32) & 0xFFFF)
            self._registers.append((value >> 16) & 0xFFFF)
            self._registers.append(value & 0xFFFF)
        else:
            self._registers.append(value & 0xFFFF)
            self._registers.append((value >> 16) & 0xFFFF)
            self._registers.append((value >> 32) & 0xFFFF)
            self._registers.append((value >> 48) & 0xFFFF)
        return self

    def add_64bit_int(self, value: int) -> "BinaryPayloadBuilder":
        """Add a 64-bit signed integer (uses 4 registers)."""
        # Convert to unsigned if negative
        if value < 0:
            value = (1 << 64) + value
        return self.add_64bit_uint(value)

    def add_64bit_float(self, value: float) -> "BinaryPayloadBuilder":
        """Add a 64-bit float (uses 4 registers)."""
        packed = struct.pack(">d", value)
        value_int = struct.unpack(">Q", packed)[0]
        return self.add_64bit_uint(value_int)

    def add_string(self, value: str) -> "BinaryPayloadBuilder":
        """Add a string (encoded as UTF-8)."""
        encoded = value.encode("utf-8")
        # Pad to even number of bytes
        if len(encoded) % 2:
            encoded += b"\x00"
        # Convert bytes to registers (2 bytes per register)
        for i in range(0, len(encoded), 2):
            reg_value = (encoded[i] << 8) | encoded[i + 1]
            self._registers.append(reg_value)
        return self

    def to_coils(self) -> List[bool]:
        """Return the bits as a list of booleans."""
        return self._bits

    def to_registers(self) -> List[int]:
        """Return the registers as a list of integers."""
        return self._registers
