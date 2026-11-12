import json
import copy
import logging
import math
import os
import struct
import tempfile
from decimal import Decimal
from pathlib import Path
from typing import List, Optional

import requests
from prettytable import PrettyTable
from modpoll_wot.acquisition import type_width
from pymodbus.client import ModbusSerialClient, ModbusTcpClient, ModbusUdpClient
from pymodbus.exceptions import ModbusException
from pymodbus.framer import FramerType

from .utils import on_threading_event, delay_thread
from .mqtt_task import MqttHandler
from .precision import names_same_raw, parse_precision, render_value


class _PayloadDecoder:
    """Decode Modbus values without pymodbus's deprecated payload helpers."""

    def __init__(self, data, *, byteorder="big", wordorder="big", coils=False):
        self.byteorder = byteorder
        self.wordorder = "big" if coils else wordorder
        if coils:
            self.data = bytearray(
                sum(
                    bool(bit) << (7 - index)
                    for index, bit in enumerate(data[i : i + 8])
                )
                for i in range(0, len(data), 8)
            )
        else:
            self.data = bytearray()
            for register in data:
                self.data.extend(register.to_bytes(2, "big"))
        self.offset = 0

    def skip_bytes(self, count):
        self.offset += count

    def _unpack(self, fmt, size):
        payload = self.data[self.offset : self.offset + size]
        self.offset += size
        if len(payload) != size:
            raise ValueError("not enough payload data")
        if self.byteorder == "little":
            payload = b"".join(payload[i : i + 2][::-1] for i in range(0, size, 2))
        if self.wordorder == "little" and size > 2:
            payload = b"".join(payload[i : i + 2] for i in range(size - 2, -1, -2))
        return struct.unpack(">" + fmt, payload)[0]

    def decode_16bit_uint(self):
        return self._unpack("H", 2)

    def decode_16bit_int(self):
        return self._unpack("h", 2)

    def decode_32bit_uint(self):
        return self._unpack("I", 4)

    def decode_32bit_int(self):
        return self._unpack("i", 4)

    def decode_64bit_uint(self):
        return self._unpack("Q", 8)

    def decode_64bit_int(self):
        return self._unpack("q", 8)

    def decode_16bit_float(self):
        return self._unpack("e", 2)

    def decode_32bit_float(self):
        return self._unpack("f", 4)

    def decode_64bit_float(self):
        return self._unpack("d", 8)

    def decode_string(self, count):
        payload = self.data[self.offset : self.offset + count]
        self.offset += count
        return bytes(payload)

    def decode_string_ordered(self, count):
        span = ((count + 1) // 2) * 2
        payload = self.data[self.offset : self.offset + span]
        self.offset += span
        if len(payload) != span:
            raise ValueError("not enough string payload")
        if self.byteorder == "little":
            payload = b"".join(payload[i : i + 2][::-1] for i in range(0, span, 2))
        if self.wordorder == "little":
            payload = b"".join(payload[i : i + 2] for i in range(span - 2, -1, -2))
        return bytes(payload[:count])

    def decode_bits(self):
        value = self.data[self.offset]
        self.offset += 1
        return [bool(value & (1 << bit)) for bit in range(8)]


SNAPSHOT_TIMESTAMP = "timestamp"


def snapshot_timestamp_conflicts(handlers) -> list:
    """Device names whose point named `timestamp` a snapshot timestamp would hide."""
    return [
        dev.name
        for handler in handlers
        for dev in handler.deviceList
        if SNAPSHOT_TIMESTAMP in dev.points
    ]


def export_modbus_handlers(handlers, file, timestamp=None) -> bool:
    """Write one complete, atomically replaced JSON snapshot for all handlers.

    The snapshot maps each device title to its point values, with null for
    points not read in this cycle. Modsim accepts it as simulation data.
    """
    data = {}
    for handler in handlers:
        for dev in handler.deviceList:
            if dev.name in data:
                handler.logger.error("Cannot export duplicate device name %s", dev.name)
                return False
            if timestamp is not None and SNAPSHOT_TIMESTAMP in dev.points:
                handler.logger.error(
                    "Cannot export --timestamp: device %s has a point named timestamp",
                    dev.name,
                )
                return False
            dev_data = {}
            for point in dev.points.values():
                if not point.valid_this_poll:
                    dev_data[point.name] = None
                    continue
                rendered = handler.render_point(point)
                handler.warn_truncated(point, rendered)
                dev_data[point.name] = rendered
            if timestamp is not None:
                dev_data[SNAPSHOT_TIMESTAMP] = timestamp
            data[dev.name] = dev_data

    target = Path(file)
    temporary = None
    try:
        fd, temporary = tempfile.mkstemp(
            prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
        )
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            json.dump(data, output, indent=2, allow_nan=False)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, target)
        return True
    except (OSError, TypeError, ValueError) as e:
        logging.getLogger(__name__).error("Error exporting data: %s", e)
        return False
    finally:
        if temporary and os.path.exists(temporary):
            try:
                os.unlink(temporary)
            except OSError:
                logging.getLogger(__name__).warning(
                    "Unable to remove temporary snapshot %s", temporary
                )


class Device:
    def __init__(self, device_name: str, device_id: int):
        self.name = device_name
        self.devid = device_id
        self.pollerList: List[Poller] = []
        self.points: dict = {}
        self.errorCount = 0
        self.pollCount = 0
        self.pollSuccess = False

    def add_point_mapping(self, point):
        self.points[point.name] = point


class Poller:
    def __init__(
        self,
        device: Device,
        function_code: int,
        start_address: int,
        size: int,
        endian: str,
    ):
        self.device = device
        self.fc = function_code
        self.start_address = start_address
        self.size = size
        self.endian = endian.lower()
        self.readablePoints: List[Point] = []
        self.disabled = False
        self.failcounter = 0
        self.logger = logging.getLogger(__name__)

    def poll(self, master) -> bool:
        try:
            result = None
            data = None
            decode_success = True

            def _call_read(method):
                return method(
                    self.start_address, count=self.size, device_id=self.device.devid
                )

            if self.fc == 1:
                result = _call_read(master.read_coils)
            elif self.fc == 2:
                result = _call_read(master.read_discrete_inputs)
            elif self.fc == 3:
                result = _call_read(master.read_holding_registers)
            elif self.fc == 4:
                result = _call_read(master.read_input_registers)

            if result and not result.isError():
                if self.fc in (1, 2):
                    data = result.bits
                    # CSV addresses for bit tables identify eight-bit groups,
                    # relative to the poll start, as in the documented examples.
                    group_count = math.ceil(self.size / 8)
                    for point in self.readablePoints:
                        offset = point.address - self.start_address
                        span = point.bit_group_width
                        if getattr(point, "physical_bits", False):
                            try:
                                count = point.bit_count
                                if (
                                    offset < 0
                                    or offset + count > self.size
                                    or offset + count > len(data)
                                ):
                                    raise ValueError("short physical bit response")
                                bits = data[offset : offset + count]
                                if point.dtype.startswith("bool"):
                                    point.update_value(
                                        bool(bits[0]) if point.scalar else list(bits)
                                    )
                                else:
                                    decoder = self._get_decoder(bits, point)
                                    self._decode_and_update_point(point, decoder)
                                if not point.valid_this_poll:
                                    decode_success = False
                            except Exception as exc:
                                point.update_value(None, valid=False)
                                decode_success = False
                                self._log_decode_failure(point, exc)
                            continue
                        if (
                            offset < 0
                            or offset + span > group_count
                            or len(data) < min((offset + span) * 8, self.size)
                        ):
                            point.update_value(None, valid=False)
                            decode_success = False
                            self.logger.error(
                                "Point %s is outside the polled bit groups",
                                point.name,
                            )
                            continue
                        try:
                            if (
                                point.dtype in ("bool", "bool8", "bool16")
                                and point.bit is None
                            ):
                                start = offset * 8
                                point.update_value(
                                    list(
                                        data[
                                            start : min(
                                                start + point.point_width * 8, self.size
                                            )
                                        ]
                                    )
                                )
                            else:
                                if (offset + span) * 8 > self.size:
                                    raise ValueError(
                                        "numeric/string bit span exceeds requested bits"
                                    )
                                decoder = self._get_decoder(
                                    data[: (self.size // 8) * 8], point
                                )
                                decoder.skip_bytes(offset)
                                self._decode_and_update_point(point, decoder)
                            if not point.valid_this_poll:
                                decode_success = False
                        except Exception as exc:
                            point.update_value(None, valid=False)
                            decode_success = False
                            self._log_decode_failure(point, exc)
                else:  # Function codes 3 and 4
                    data = result.registers
                    # Sort refs by address to ensure predictable decoding order
                    sorted_points = sorted(self.readablePoints, key=lambda r: r.address)
                    for point in sorted_points:
                        # Create and position a new decoder for each point for robustness
                        decoder = self._get_decoder(data, point)
                        offset_bytes = (point.address - self.start_address) * 2
                        if offset_bytes < 0:
                            self.logger.warning(
                                f"Point {point.name} address {point.address} is outside of poller range starting at {self.start_address}"
                            )
                            point.update_value(None, valid=False)
                            decode_success = False
                            continue
                        if offset_bytes // 2 + point.point_width > len(data):
                            point.update_value(None, valid=False)
                            decode_success = False
                            self.logger.error(
                                "Short register response for %s", point.name
                            )
                            continue
                        decoder.skip_bytes(offset_bytes)
                        try:
                            self._decode_and_update_point(point, decoder)
                            if not point.valid_this_poll:
                                decode_success = False
                        except Exception as exc:
                            point.update_value(None, valid=False)
                            decode_success = False
                            self._log_decode_failure(point, exc)
                self.update_statistics(decode_success)
                return decode_success
        except ModbusException:
            self.logger.error(
                f"Modbus exception: {self.device.name} {self.fc} {self.start_address} {self.size}"
            )

        self.update_statistics(False)
        for point in self.readablePoints:
            point.update_value(None)
        return False

    def _get_decoder(self, data, point=None):
        endian = getattr(point, "endian", None) or self.endian
        byteorder = "little" if endian.upper().startswith("LE_") else "big"
        wordorder = "little" if endian.upper().endswith("_LE") else "big"
        return _PayloadDecoder(
            data,
            byteorder=byteorder,
            wordorder=wordorder,
            coils=self.fc in (1, 2),
        )

    def _log_decode_failure(self, point: "Point", exc: Exception):
        """Bad register data is a data event, not a program error: one line, stack at DEBUG."""
        self.logger.error(
            "Failed to decode point %s: %s: %s", point.name, type(exc).__name__, exc
        )
        self.logger.debug("Decode failure details for %s", point.name, exc_info=True)

    def _decode_and_update_point(self, point: "Point", decoder: _PayloadDecoder):
        if getattr(point, "scalar", False) and point.dtype == "uint16":
            point.update_value(bool(decoder.decode_16bit_uint()))
            return
        if point.dtype == "bool" and point.bit is not None:
            # Bit points read a 16-bit register and extract one bit.
            register_value = decoder.decode_16bit_uint()
            bit_value = (register_value >> point.bit) & 1
            point.update_value(bool(bit_value))
            return

        decode_methods = {
            "uint16": decoder.decode_16bit_uint,
            "int16": decoder.decode_16bit_int,
            "uint32": decoder.decode_32bit_uint,
            "int32": decoder.decode_32bit_int,
            "uint64": decoder.decode_64bit_uint,
            "int64": decoder.decode_64bit_int,
            "float16": decoder.decode_16bit_float,
            "float32": decoder.decode_32bit_float,
            "float64": decoder.decode_64bit_float,
            "bool8": decoder.decode_bits,
            "bool": decoder.decode_bits,
            "bool16": lambda: decoder.decode_bits() + decoder.decode_bits(),
        }

        if point.dtype in decode_methods:
            point.update_value(decode_methods[point.dtype]())
        elif point.dtype.startswith("string"):
            count = int(point.dtype[6:])
            payload = (
                decoder.decode_string_ordered(count)
                if getattr(point, "endian", None) is not None
                and not getattr(point, "physical_bits", False)
                else decoder.decode_string(count)
            )
            point.update_value(payload.decode("utf-8").rstrip("\x00"))

    def add_readable_point(self, point: "Point"):
        if not any(existing is point for existing in self.readablePoints):
            self.readablePoints.append(point)

    def update_statistics(self, success: bool):
        if success:
            self.failcounter = 0
            self.device.pollSuccess = True
        else:
            self.failcounter += 1
            self.device.pollSuccess = False


def _multiplier(scale):
    """The float the engine computes with, and the exact decimal of it.

    An unusable multiplier leaves the reading unscaled, as it always did.
    """
    if scale is None:
        return None, None
    try:
        return float(scale), Decimal(str(scale))
    except (TypeError, ValueError, ArithmeticError):
        return scale, None


class Point:
    def __init__(
        self,
        device: Device,
        point_name: str,
        point_addr: str,
        dtype: str,
        rw: str,
        unit: str,
        scale: Optional[Decimal | float],
    ):
        self.device = device
        self.name = point_name
        self.bit: Optional[int] = None
        try:
            if ":" in point_addr:
                addr, bit = point_addr.split(":")
                self.address = int(addr, 0)
                self.bit = int(bit)
                if not 0 <= self.bit <= 15:
                    raise ValueError("Bit index must be between 0 and 15")
            else:
                self.address = int(point_addr, 0)
        except ValueError as e:
            raise ValueError(f"Invalid address format for {point_name}: {e}") from e
        self.dtype = dtype.lower()
        # Validate that bit syntax is only used with bool dtype
        if self.bit is not None and self.dtype != "bool":
            raise ValueError(
                f"Bit index syntax (address:bit) can only be used with dtype 'bool', "
                f"but point {point_name} has dtype '{self.dtype}'"
            )
        self.point_width = type_width(self.dtype)
        self.rw = rw.lower()
        self.unit = unit
        # The multiplier reaches the engine as a float, so the value is
        # computed exactly as before.  Its shortest decimal form is kept
        # separately, because that is the form the profile contract uses to
        # map an engineering value back to its raw register value.
        self.scale, self.exact_multiplier = _multiplier(scale)
        self.val = None
        self.raw_val = None
        self.last_val = None
        self.valid_this_poll = False

    def __repr__(self):
        addr = f"{self.address}:{self.bit}" if self.bit is not None else self.address
        return f"<Point {self.name}@{addr}>"

    @property
    def bit_group_width(self):
        return type_width(self.dtype, bit_table=True)

    def update_value(self, v, valid=True):
        self.raw_val = v
        if self.scale is not None and not isinstance(v, bool):
            try:
                v = v * float(self.scale)
            except (ValueError, TypeError):
                pass
        if isinstance(v, float) and not math.isfinite(v):
            logging.getLogger(__name__).warning(
                "Non-finite value for point %s on device %s",
                self.name,
                self.device.name,
            )
            v = None
            valid = False
        self.last_val = self.val
        self.val = v
        self.valid_this_poll = valid and v is not None


class _ConfigLogAdapter(logging.LoggerAdapter):
    def process(self, message, kwargs):
        return "[%s] %s" % (self.extra["config"], message), kwargs


class ModbusHandler:
    def __init__(
        self,
        modbus_client,
        config_file: str,
        mqtt_handler: Optional[MqttHandler] = None,
        timeout: float = 3.0,
        interval: float = 0.5,
        daemon: bool = False,
        mqtt_publish_topic_pattern: Optional[str] = None,
        mqtt_diagnostics_topic_pattern: Optional[str] = None,
        mqtt_single_publish: bool = False,
        autoremove: bool = False,
        unit_id: Optional[int] = None,
        instance_host: Optional[str] = None,
        instance_port: Optional[int] = None,
        instance_parameters=None,
        precision: Optional[int] = None,
        config_kind: Optional[str] = None,
    ):
        self.modbus_client = modbus_client
        self.config_file = config_file
        self.config_kind = config_kind
        self.unit_id = unit_id
        self.instance_host = instance_host
        self.instance_port = instance_port
        self.instance_parameters = instance_parameters
        self.model = None
        self.mqtt_handler = mqtt_handler
        self.timeout = timeout
        self.interval = interval
        self.daemon = daemon
        self.mqtt_publish_topic_pattern = mqtt_publish_topic_pattern
        self.mqtt_diagnostics_topic_pattern = mqtt_diagnostics_topic_pattern
        self.mqtt_single_publish = mqtt_single_publish
        self.autoremove = autoremove
        self.connected = False
        self.deviceList: List[Device] = []
        # None keeps the automatic mode; a count rounds every float to at
        # most that many decimals.
        self.precision = precision
        self._truncation_warned: set = set()
        self.logger = _ConfigLogAdapter(
            logging.getLogger(__name__), {"config": config_file}
        )

    def load_config(self) -> bool:
        from .config_loader import ConfigUsageError, load_devices

        self.logger.info(f"Loading config from: {self.config_file}")
        try:
            self.deviceList, self.model = load_devices(
                self.config_file,
                kind=self.config_kind,
                timeout=self.timeout,
                unit_id=self.unit_id,
                host=self.instance_host,
                port=self.instance_port,
                parameters=self.instance_parameters,
                logger=self.logger,
            )
        except ConfigUsageError:
            raise
        except (ValueError, OSError, requests.RequestException) as exc:
            self.logger.error("Invalid configuration: %s", exc)
            return False
        if not self.deviceList:
            self.logger.error("No device found in the config file. Skipping.")
            return False
        self.logger.info("Added %d device(s)", len(self.deviceList))
        return True

    def connect(self) -> bool:
        if not self.connected:
            self.connected = self.modbus_client.connect()
        return self.connected

    def disconnect(self):
        if self.modbus_client and self.connected:
            self.modbus_client.close()
            self.connected = False

    def _record_poller_result(self, poller, success, previous_failures):
        poller.failcounter = 0 if success else previous_failures + 1
        if self.autoremove and poller.failcounter >= 3:
            poller.disabled = True
            self.logger.warning(
                "Disabled poller for %s at address %s after 3 consecutive failures; restart to retry",
                poller.device.name,
                poller.start_address,
            )

    def poll(self):
        for dev in self.deviceList:
            dev.pollSuccess = False
            for point in dev.points.values():
                point.valid_this_poll = False
        if not self.connect():
            self.logger.error("Failed to connect to Modbus client")
            for dev in self.deviceList:
                for point in dev.points.values():
                    point.update_value(None, valid=False)
                active = [p for p in dev.pollerList if not p.disabled]
                if active:
                    dev.pollCount += 1
                    dev.errorCount += 1
                for poller in active:
                    previous_failures = poller.failcounter
                    poller.update_statistics(False)
                    self._record_poller_result(poller, False, previous_failures)
            return
        try:
            for dev in self.deviceList:
                self.logger.debug(f"Polling device {dev.name} ...")
                pollers = [p for p in dev.pollerList if not p.disabled]
                poll_success = bool(pollers)
                for p in pollers:
                    previous_failures = p.failcounter
                    try:
                        succeeded = p.poll(self.modbus_client)
                        poll_success = succeeded and poll_success
                    except Exception:
                        self.logger.exception("Unexpected polling error")
                        succeeded = False
                        poll_success = False
                        for point in p.readablePoints:
                            point.update_value(None, valid=False)
                    self._record_poller_result(p, succeeded, previous_failures)
                    if on_threading_event():
                        return
                    delay_thread(timeout=self.interval)
                dev.pollSuccess = poll_success
                if pollers:
                    # One poll cycle per device, however many pollers it has.
                    dev.pollCount += 1
                    if not poll_success:
                        dev.errorCount += 1
        finally:
            self.disconnect()
            if not self.daemon:
                self.print_results()

    def write_coil(self, device_name: str, address: int, value) -> bool:
        for dev in self.deviceList:
            if dev.name == device_name:
                try:
                    if not _valid_write_address(address):
                        self.logger.warning(f"Invalid coil address: {address}")
                        return False
                    if type(value) not in (bool, int) or value not in (0, 1):
                        self.logger.warning(f"Invalid coil value: {value}")
                        return False
                    if not self.connect():
                        return False
                    result = self.modbus_client.write_coil(
                        address, bool(value), device_id=dev.devid
                    )
                    return not result.isError()
                except (
                    ModbusException,
                    OSError,
                    TypeError,
                    ValueError,
                    AttributeError,
                ) as e:
                    self.logger.error(f"Error writing coil: {e}")
                    return False
                finally:
                    self.disconnect()
        self.logger.error(f"Device {device_name} not found")
        return False

    def write_register(self, device_name, address: int, value) -> bool:
        for dev in self.deviceList:
            if dev.name == device_name:
                try:
                    if not _valid_write_address(address):
                        self.logger.warning(f"Invalid register address: {address}")
                        return False
                    if isinstance(value, list):
                        if (
                            not value
                            or len(value) > 123
                            or any(
                                type(item) is not int or not 0 <= item <= 65535
                                for item in value
                            )
                            or address + len(value) > 65536
                        ):
                            self.logger.warning(
                                "Invalid holding register values or span"
                            )
                            return False
                        write = self.modbus_client.write_registers
                        args = (address, value)
                    elif type(value) is int and 0 <= value <= 65535:
                        write = self.modbus_client.write_register
                        args = (address, value)
                    else:
                        self.logger.warning(f"Invalid holding register value: {value}")
                        return False
                    if not self.connect():
                        return False
                    result = write(*args, device_id=dev.devid)
                    return not result.isError()
                except (
                    ModbusException,
                    OSError,
                    TypeError,
                    ValueError,
                    AttributeError,
                ) as e:
                    self.logger.error(f"Error writing register: {e}")
                    return False
                finally:
                    self.disconnect()
        self.logger.error(f"Device {device_name} not found")
        return False

    def render_point(self, point):
        """The value the console, the MQTT payload and the snapshot show.

        All three read the point through this method, so one reading never
        appears as two different numbers.
        """
        return render_value(
            point.val,
            self.precision,
            dtype=point.dtype,
            raw=point.raw_val,
            multiplier=point.exact_multiplier,
        )

    def warn_truncated(self, point, rendered) -> None:
        """Warn once when rounding a scaled reading changed its raw value.

        The exported snapshot doubles as simulation data, so a truncated
        scaled value that no longer names its raw register value silently
        changes what a replay serves.
        """
        if self.precision is None or point.exact_multiplier is None:
            return
        raw = point.raw_val
        if raw is None or isinstance(raw, bool) or not isinstance(raw, int):
            return
        if names_same_raw(rendered, raw, point.exact_multiplier):
            return
        key = (point.device.name, point.name)
        if key in self._truncation_warned:
            return
        self._truncation_warned.add(key)
        self.logger.warning(
            "Precision %d rounds point %s of device %s to %r, which no longer "
            "names raw value %s; replaying the exported snapshot serves a "
            "different register value.",
            self.precision,
            point.name,
            point.device.name,
            rendered,
            raw,
        )

    def print_results(self):
        for dev in self.deviceList:
            table = PrettyTable()
            table.field_names = ["Point", "Value", "Unit"]
            table.align["Point"] = "l"
            table.align["Value"] = "r"
            table.align["Unit"] = "l"
            for point in dev.points.values():
                value = self.render_point(point) if point.valid_this_poll else None
                table.add_row(
                    [
                        point.name,
                        value,
                        point.unit or "",
                    ]
                )
            print(f"\nDevice: {dev.name}")
            print(table)

    def publish_data(self, timestamp=None, on_change=False):
        if not self.mqtt_handler or not self.mqtt_publish_topic_pattern:
            return

        for dev in self.deviceList:
            payload = {}
            for point in dev.points.values():
                if not point.valid_this_poll:
                    continue
                if not on_change or point.val != point.last_val:
                    point_val = self.render_point(point)
                    key = f"{point.name}|{point.unit}" if point.unit else point.name
                    payload[key] = point_val

                    if self.mqtt_single_publish:
                        topic = f"{self.mqtt_publish_topic_pattern.replace('{{device_name}}', dev.name)}/{point.name}"
                        if isinstance(point_val, list):
                            for i, entry in enumerate(point_val):
                                self.mqtt_handler.publish(f"{topic}/{i}", entry)
                        else:
                            self.mqtt_handler.publish(topic, point_val)

            if payload and not self.mqtt_single_publish:
                if timestamp is not None:
                    payload["timestamp"] = timestamp
                topic = self.mqtt_publish_topic_pattern.replace(
                    "{{device_name}}", dev.name
                )
                self.mqtt_handler.publish(topic, json.dumps(payload))

    def publish_diagnostics(self):
        if not self.mqtt_handler:
            return
        if not self.mqtt_diagnostics_topic_pattern:
            return
        for dev in self.deviceList:
            payload = {
                "poll_count": dev.pollCount,
                "error_count": dev.errorCount,
                "last_poll_success": dev.pollSuccess,
            }
            topic = self.mqtt_diagnostics_topic_pattern.replace(
                "{{device_name}}", dev.name
            )
            self.mqtt_handler.publish(topic, json.dumps(payload))

    def export(self, file, timestamp=None):
        return export_modbus_handlers([self], file, timestamp)

    def close(self):
        self.disconnect()
        self.modbus_client = None

    def get_device_list(self) -> List[Device]:
        return self.deviceList


def setup_modbus_handlers(args, mqtt_handler: Optional[MqttHandler] = None):
    modbus_handlers = []
    current_handler = None
    device_names = set()
    parameters = None
    if args.param:
        import modpoll_wot

        if not hasattr(modpoll_wot, "parse_parameters"):
            raise ValueError("TM parameters require the profile 0.2 interpreter")
        parameters = modpoll_wot.parse_parameters(args.param)
    try:
        config_specs = (
            [(location, None) for location in args.config]
            + [(location, "tm") for location in args.thing_model]
            + [(location, "td") for location in args.thing_description]
        )
        for config_file, config_kind in config_specs:
            current_handler = ModbusHandler(
                None,
                config_file,
                mqtt_handler,
                timeout=args.timeout,
                interval=args.interval,
                daemon=args.daemon,
                mqtt_publish_topic_pattern=args.mqtt_publish_topic_pattern,
                mqtt_diagnostics_topic_pattern=args.mqtt_diagnostics_topic_pattern,
                mqtt_single_publish=args.mqtt_single,
                autoremove=args.autoremove,
                unit_id=args.unit_id,
                instance_host=args.tcp,
                instance_port=args.tcp_port,
                instance_parameters=parameters,
                precision=parse_precision(getattr(args, "precision", None)),
                config_kind=config_kind,
            )
            if current_handler.load_config():
                effective_args = copy.copy(args)
                endpoint = getattr(current_handler.model, "endpoint", None)
                if endpoint is not None:
                    if args.serial or args.udp:
                        raise ValueError(
                            "Use an unbound TM for serial/UDP; this configuration describes a TCP instance"
                        )
                    effective_args.tcp, effective_args.tcp_port = endpoint
                current_handler.modbus_client = _create_modbus_client(effective_args)
                names = {device.name for device in current_handler.get_device_list()}
                duplicates = names & device_names
                if duplicates:
                    raise ValueError(
                        "Duplicate device names across configurations: "
                        + ", ".join(sorted(duplicates))
                    )
                device_names.update(names)
                modbus_handlers.append(current_handler)
            else:
                current_handler.close()
            current_handler = None
    except Exception:
        for handler in (
            [current_handler] if current_handler is not None else []
        ) + modbus_handlers:
            try:
                handler.close()
            except Exception:
                logging.getLogger(__name__).exception(
                    "Failed to close handler after setup error"
                )
        raise
    return modbus_handlers


def _valid_write_address(address) -> bool:
    return type(address) is int and 0 <= address <= 65535


def _create_modbus_client(args):
    transport = _determine_transport(args)

    if transport == "serial":
        framer = _resolve_framer("serial", args.framer)
        return _create_serial_client(args, args.serial, framer)

    if transport == "tcp":
        framer = _resolve_framer("tcp", args.framer)
        return _create_tcp_client(args, framer)

    if transport == "udp":
        framer = _resolve_framer("udp", args.framer)
        return _create_udp_client(args, framer)

    raise ValueError("No communication method specified.")


def _create_serial_client(args, port, framer):
    if not port:
        raise ValueError("Serial port/URL must be provided for serial transports.")
    parity = _get_parity(args.serial_parity)
    client_args = {
        "port": port,
        "baudrate": int(args.serial_baud),
        "bytesize": 8,
        "parity": parity,
        "stopbits": 1,
        "timeout": args.timeout,
    }
    if framer:
        client_args["framer"] = framer
    return ModbusSerialClient(**client_args)


def _create_tcp_client(args, framer):
    client_args = {
        "host": args.tcp,
        "port": 502 if args.tcp_port is None else args.tcp_port,
        "timeout": args.timeout,
    }
    if framer:
        client_args["framer"] = framer
    return ModbusTcpClient(**client_args)


def _create_udp_client(args, framer):
    client_args = {
        "host": args.udp,
        "port": args.udp_port,
        "timeout": args.timeout,
    }
    if framer:
        client_args["framer"] = framer
    return ModbusUdpClient(**client_args)


def _get_parity(serial_parity):
    if serial_parity == "odd":
        return "O"
    elif serial_parity == "even":
        return "E"
    else:
        return "N"


def _determine_transport(args):
    transports = []
    if args.serial:
        transports.append("serial")
    if args.tcp:
        transports.append("tcp")
    if args.udp:
        transports.append("udp")

    if not transports:
        raise ValueError("No communication method specified.")
    if len(transports) > 1:
        raise ValueError(
            "Multiple communication methods specified; pick one of --serial/--tcp/--udp (alias: --rtu)."
        )
    return transports[0]


def _resolve_framer(transport, framer_name):
    """Resolve the requested framer using the PyModbus client API enum."""

    if framer_name == "default":
        # Let pymodbus choose its transport defaults:
        # Serial -> RTU framer; TCP/UDP -> socket framer.
        return None

    framer_map = {
        "rtu": FramerType.RTU,
        "ascii": FramerType.ASCII,
        "socket": FramerType.SOCKET,
    }
    allowed = {
        "serial": {"rtu", "ascii"},
        "tcp": {"socket"},
        "udp": {"socket"},
    }

    if transport in ("tcp", "udp"):
        transport_key = transport
    else:
        transport_key = "serial"

    if framer_name not in allowed[transport_key]:
        raise ValueError(
            f"Framer '{framer_name}' is not valid for transport '{transport_key}'."
        )

    framer_cls = framer_map.get(framer_name)
    if framer_cls is None:
        raise ValueError(
            f"Framer '{framer_name}' is not available with the installed pymodbus version."
        )
    return framer_cls
