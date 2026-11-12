"""One float rendering rule for the console, MQTT payloads and JSON exports.

The terminal table, the MQTT payload and the JSON snapshot show the same
number for a point, so a reader never sees two different values for one
reading.

The automatic mode keeps every value at the precision its source carries:
the exact decimal of a scaled reading, the shortest decimal naming the same
value at the register width, and the value itself for integers.  An explicit
count rounds floats to at most that many decimals; the caller is warned when
that truncation stops the value from naming the same raw register value,
because an exported snapshot has to invert back to that raw value.
"""

from decimal import Decimal, InvalidOperation, localcontext
import math
import struct

from modpoll_wot import DataError, scaled_raw


AUTO = "auto"

_WIDTH_FORMATS = {"float16": ">e", "float32": ">f"}


def parse_precision(text):
    """Return None for the automatic mode, or a non-negative decimal count."""
    if text is None:
        return None
    if isinstance(text, bool):
        raise ValueError(f"invalid precision {text!r}")
    if isinstance(text, int):
        count = text
    else:
        stripped = str(text).strip().lower()
        if stripped in ("", AUTO):
            return None
        try:
            count = int(stripped)
        except ValueError:
            raise ValueError(f"invalid precision {text!r}") from None
    if count < 0:
        raise ValueError("precision must not be negative")
    return count


def render_value(value, precision, *, dtype=None, raw=None, multiplier=None):
    """Return the value as the console, MQTT and JSON output should show it.

    `precision` is None for the automatic mode.  `raw` is the decoded value
    before the multiplier was applied and `multiplier` its exact decimal,
    which together let a scaled reading render without float artefacts.
    """
    if isinstance(value, bool) or not isinstance(value, float):
        return value
    exact = _exact_scaled(raw, multiplier)
    if exact is not None:
        if precision is not None:
            return _as_float(_quantize(exact, precision), value)
        rendered = _as_float(exact, None)
        if rendered is None:
            return value
        return rendered if names_same_raw(rendered, raw, multiplier) else value
    if precision is None:
        return _shortest_at_width(value, dtype)
    return round(value, precision)


def names_same_raw(value, raw, multiplier):
    """Whether the value still names the same raw register value."""
    if multiplier is None or raw is None:
        return True
    try:
        return scaled_raw(value, multiplier) == raw
    except (DataError, ValueError, ZeroDivisionError, OverflowError):
        return False


def _exact_scaled(raw, multiplier):
    """The exact decimal of a scaled reading, or None when it does not apply."""
    if multiplier is None or raw is None:
        return None
    if isinstance(raw, bool) or not isinstance(raw, int):
        return None
    try:
        return Decimal(raw) * multiplier
    except (InvalidOperation, TypeError, ValueError):
        return None


def _quantize(exact, precision):
    """Round an exact decimal to the given number of decimals."""
    exponent = Decimal(1).scaleb(-precision)
    try:
        with localcontext() as context:
            context.prec = max(len(exact.as_tuple().digits) + precision + 2, 28)
            return exact.quantize(exponent)
    except (InvalidOperation, OverflowError, ValueError):
        return exact


def _as_float(exact, fallback):
    """The float of an exact decimal, or the fallback when it is not finite."""
    try:
        rendered = float(exact)
    except (OverflowError, ValueError):
        return fallback
    return rendered if math.isfinite(rendered) else fallback


def _shortest_at_width(value, dtype):
    """The shortest decimal that names the same value at the register width."""
    fmt = _WIDTH_FORMATS.get(dtype)
    if fmt is None:
        return value
    try:
        packed = struct.pack(fmt, value)
        if struct.unpack(fmt, packed)[0] != value:
            return value
    except (struct.error, OverflowError, ValueError):
        return value
    for digits in range(1, 18):
        candidate = float(f"{value:.{digits}g}")
        try:
            if struct.pack(fmt, candidate) == packed:
                return candidate
        except (struct.error, OverflowError, ValueError):
            continue
    return value
