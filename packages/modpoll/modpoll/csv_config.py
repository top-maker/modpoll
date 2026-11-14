"""Load v1 CSV configurations into the shared polling engine.

The v1 ``device``/``poll``/``ref`` row format is accepted again: ``--config``
detects CSV versus WoT TM/TD JSON from the file content, and this module turns
CSV rows into the same Device, Poller and Point objects the WoT loader
produces, so both formats share one polling, output and export path.

Row semantics follow v1: point names replace ASCII spaces with underscores, a
blank access column defaults to ``r``, and the scale column multiplies the
decoded value. Bit-table point addresses identify eight-bit groups, as the
documented v1 examples always did.
"""

import csv
import io
import logging
import math

DEVICE_COL_MIN = 3
POLL_COL_MIN = 5
REF_COL_MIN = 5

_FUNCTION_CODES = {
    "coil": 1,
    "discrete_input": 2,
    "holding_register": 3,
    "input_register": 4,
}

_ENDIAN_VALUES = {"BE_BE", "BE_LE", "LE_BE", "LE_LE"}


def parse_csv(text, *, source, unit_id=None, logger=None):
    """Parse v1 CSV rows into a device list.

    ``unit_id`` overrides the per-device ID column when given. Duplicate
    device names abort the load; every other bad row is reported and skipped,
    matching the v1 loader.
    """
    from .modbus_task import Device

    logger = logger or logging.getLogger(__name__)
    device_list = []
    current_device = None
    current_poller = None
    duplicate_devices = []
    reader = csv.reader(io.StringIO(text))
    for line_number, row in enumerate(reader, start=1):
        if not row or all(cell.strip() == "" for cell in row):
            continue
        try:
            if "device" in row[0].lower():
                current_device, current_poller = None, None
                if len(row) < DEVICE_COL_MIN:
                    logger.error(
                        "Config line %s: invalid device configuration", line_number
                    )
                    continue
                device_name = row[1].strip()
                if any(device.name == device_name for device in device_list):
                    logger.error(
                        "Config line %s: duplicate device name %s",
                        line_number,
                        device_name,
                    )
                    duplicate_devices.append((line_number, device_name))
                    continue
                try:
                    device_id = int(row[2], 0)
                except ValueError:
                    logger.error(
                        "Config line %s: invalid device ID for %s",
                        line_number,
                        device_name,
                    )
                    continue
                if not 1 <= device_id <= 254:
                    logger.error(
                        "Config line %s: device ID out of range for %s",
                        line_number,
                        device_name,
                    )
                    continue
                current_device = Device(device_name, device_id)
                device_list.append(current_device)
            elif "poll" in row[0].lower():
                if not current_device:
                    logger.error("Config line %s: no device to add poller", line_number)
                    current_poller = None
                    continue
                current_poller = _create_poller(row, current_device, logger)
                if current_poller:
                    current_device.pollerList.append(current_poller)
                else:
                    logger.error("Config line %s: poller ignored", line_number)
            elif "ref" in row[0].lower():
                if not current_device or not current_poller:
                    logger.error(
                        "Config line %s: reference has no valid device/poller",
                        line_number,
                    )
                    continue
                point = _create_point(row, current_device, logger)
                if point is None:
                    logger.error("Config line %s: reference ignored", line_number)
                    continue
                if point.name in current_device.points:
                    logger.error(
                        "Config line %s: duplicate reference name %s",
                        line_number,
                        point.name,
                    )
                    continue
                if _validate_point(point, current_poller, logger):
                    if "r" in point.rw.lower():
                        current_poller.add_readable_point(point)
                    current_device.add_point_mapping(point)
                else:
                    logger.error(
                        "Config line %s: reference failed validation", line_number
                    )
            else:
                logger.warning(
                    "Config line %s: unknown row type %r", line_number, row[0]
                )
        except Exception as exc:
            logger.error("Config line %s: invalid row %r: %s", line_number, row, exc)
    if duplicate_devices:
        details = ", ".join(
            "%s (line %s)" % (name, line) for line, name in duplicate_devices
        )
        from .config_loader import ConfigUsageError

        raise ConfigUsageError(f"Duplicate device names in {source}: {details}")
    if unit_id is not None:
        for device in device_list:
            device.devid = unit_id
    return device_list


def _create_poller(row, device, logger):
    if len(row) < POLL_COL_MIN:
        logger.error("Invalid poller configuration")
        return None
    function_code = _FUNCTION_CODES.get(row[1].lower())
    if function_code is None:
        logger.warning("Unknown function code (%s) ignoring poller.", row[1])
        return None
    try:
        start_address = int(row[2], 0)
        size = int(row[3], 0)
    except ValueError:
        logger.error("Invalid start address or size for poller")
        return None
    endian = row[4].upper()
    if endian not in _ENDIAN_VALUES:
        logger.error("Invalid endian setting: %s", endian)
        return None
    if not 0 <= start_address <= 65535:
        logger.error("Invalid poller start address: %s", start_address)
        return None
    if not _validate_poller_size(function_code, size, logger):
        return None
    if start_address + size > 65536:
        logger.error("Poller address range exceeds Modbus address space")
        return None
    from .modbus_task import Poller

    return Poller(device, function_code, start_address, size, endian)


def _validate_poller_size(function_code, size, logger):
    if size <= 0:
        logger.error("Poller size must be positive: %s", size)
        return False
    if function_code in (1, 2) and size > 2000:
        logger.error(
            f"Too many coils/discrete inputs (max. 2000): {size}. Ignoring poller."
        )
        return False
    if function_code in (3, 4) and size > 125:
        logger.error(f"Too many registers (max. 125): {size}. Ignoring poller.")
        return False
    return True


def _create_point(row, device, logger):
    if len(row) < REF_COL_MIN:
        logger.error("Invalid reference configuration")
        return None
    ref_name = row[1].replace(" ", "_")
    address = row[2]
    dtype = row[3].lower()
    rw = (row[4] or "r").lower()
    if rw not in {"r", "w", "rw"}:
        logger.error("Invalid read/write mode for reference %s", ref_name)
        return None
    unit = row[5] if len(row) > 5 and row[5] else None
    try:
        scale = float(row[6]) if len(row) > 6 and row[6] else None
        if scale is not None and not math.isfinite(scale):
            raise ValueError("scale must be finite")
    except ValueError:
        logger.error("Invalid scale for reference %s", ref_name)
        return None
    from .modbus_task import Point

    try:
        return Point(device, ref_name, address, dtype, rw, unit, scale)
    except ValueError as exc:
        # Covers address format, bit selectors on non-bool types and
        # unsupported dtypes from the shared width table.
        logger.error("Invalid reference %s: %s", ref_name, exc)
        return None


def _validate_point(point, poller, logger):
    if poller.fc in (1, 2):
        if point.bit is not None:
            logger.warning("Bit selectors require a register poller: %s", point.name)
            return False
        group_count = math.ceil(poller.size / 8)
        if not (
            poller.start_address <= point.address
            and point.address + point.bit_group_width - 1
            < poller.start_address + group_count
        ):
            logger.warning(
                f"Reference {point.name} failed to pass sanity check, ignoring it."
            )
            return False
        return True
    if not (
        poller.start_address <= point.address
        and point.address + point.point_width - 1 < poller.start_address + poller.size
    ):
        logger.warning(
            f"Reference {point.name} failed to pass sanity check, ignoring it."
        )
        return False
    return True
