"""Independent device state, local behavior hooks and atomic protocol access."""

import asyncio
import copy
import importlib.util
import inspect
import logging
import math
import random
from typing import AbstractSet, Any

from pymodbus.constants import ExcCodes

from .wot import FUNCTIONS
from .codec import Codec

_LOG = logging.getLogger(__name__)


class Device:
    """Property API for profile 0.2 wire mappings.

    Internal updates can change read-only measurements; Modbus writes cannot.
    Hooks are synchronous and must not block. Each instance has its own module.
    """

    def __init__(self, model: Any, cells: Any, schemas: Any, access: Any) -> None:
        self.unit_id = model.unit_id
        self.name = model.title
        self.cells = cells
        self.access = access
        self.schemas = schemas
        self.members = {
            member.property: (group, member)
            for group in model.groups
            for member in group.members
        }
        self.codecs = {
            name: Codec(group, member, schemas[name])
            for name, (group, member) in self.members.items()
        }
        self.write_masks: dict[str, dict[int, int]] = {}
        self.random = random.Random(0)
        self.parameters: dict[str, Any] = {}
        self.script: Any = None
        self.tick_interval = 1.0
        self.generators: dict[str, Any] = {}
        self.bindings: dict[str, str] = {}
        self.write_policy = "hold"
        self.held: set[str] = set()

    def get(self, name: str) -> Any:
        """Read the current property value, including previous client writes."""
        return self.codecs[name].decode(self.cells)

    def set(self, name: str, value: Any) -> None:
        """Update a measurement or output by property name."""
        self.set_many({name: value})

    def affected(self, touched: AbstractSet[tuple[str, int]]) -> list[str]:
        return [
            name
            for name, codec in self.codecs.items()
            if any(
                (codec.table, i) in touched
                for i in range(codec.start, codec.start + codec.span)
            )
        ]

    def validate_cells(self, touched: AbstractSet[tuple[str, int]]) -> dict[str, Any]:
        changes = {}
        for name in self.affected(touched):
            value = self.get(name)
            self.codecs[name].validate(value)
            changes[name] = value
        return changes

    def set_many(self, values: dict[str, Any], *, initializing: bool = False) -> None:
        """Validate spans and aliases before atomically committing raw cells."""
        updates: dict[tuple[str, int], tuple[int, int]] = {}
        for name, value in values.items():
            if name not in self.codecs:
                raise ValueError(f"{self.name}: unknown property {name}")
            codec = self.codecs[name]
            for offset, (raw, mask) in enumerate(codec.encode(value)):
                key = (codec.table, codec.start + offset)
                previous, owned = updates.get(key, (0, 0))
                if (previous ^ raw) & owned & mask:
                    raise ValueError(f"{name}: conflicting alias values")
                updates[key] = ((previous & ~mask) | (raw & mask), owned | mask)
        old = {
            (table, address): self.cells[table][address] for table, address in updates
        }
        try:
            for (table, address), (raw, mask) in updates.items():
                value = (int(self.cells[table][address]) & ~mask) | (raw & mask)
                self.cells[table][address] = (
                    bool(value) if table in ("coil", "discrete_input") else value
                )
            if initializing:
                for name in values:
                    self.codecs[name].validate(self.get(name))
            else:
                self.validate_cells(set(updates))
        except Exception:
            for (table, address), raw in old.items():
                self.cells[table][address] = raw
            raise

    def hook(self, name: str, *args: Any) -> None:
        callback = getattr(self.script, name, None)
        if callback:
            result = callback(self, *args)
            if inspect.isawaitable(result):
                if inspect.iscoroutine(result):
                    result.close()
                raise ValueError(f"{name}: script hooks must be synchronous")

    def load_script(self, path: str, source: bytes | None = None) -> None:
        spec = importlib.util.spec_from_file_location(
            f"modsim_behavior_{self.unit_id}", path
        )
        if spec is None or spec.loader is None:
            raise ValueError(f"cannot load script: {path}")
        self.script = importlib.util.module_from_spec(spec)
        if source is None:
            spec.loader.exec_module(self.script)
        else:
            exec(compile(source, path, "exec"), self.script.__dict__)
        for name in ("initialize", "tick", "on_write"):
            callback = getattr(self.script, name, None)
            if callback is not None and (
                not callable(callback) or inspect.iscoroutinefunction(callback)
            ):
                raise ValueError(f"{path}: {name} must be a synchronous function")

    def advance(self, elapsed: float, dt: float) -> None:
        values = {}
        for name, rule in self.generators.items():
            if self.write_policy == "hold" and name in self.held:
                continue
            kind = rule["kind"]
            if kind == "constant":
                value = rule["value"]
            elif kind == "sine":
                value = rule["center"] + rule["amplitude"] * math.sin(
                    2 * math.pi * elapsed / rule["period"]
                )
            elif kind == "ramp":
                value = rule["start"] + rule["rate"] * elapsed
                value = min(rule["maximum"], max(rule["minimum"], value))
            elif kind == "noise":
                value = (
                    self.random.randint(
                        math.ceil(rule["minimum"]), math.floor(rule["maximum"])
                    )
                    if self.schemas[name].get("type") == "integer"
                    else self.random.uniform(rule["minimum"], rule["maximum"])
                )
            else:
                raise ValueError(f"unknown generator: {kind}")
            if self.schemas[name].get("type") == "integer" and type(value) is not bool:
                value = round(value)
            values[name] = value
        self.set_many(values)
        self.hook("tick", elapsed, dt)
        self.set_many(
            {target: self.get(source) for target, source in self.bindings.items()}
        )

    async def run(self) -> None:
        loop = asyncio.get_running_loop()
        start = previous = loop.time()
        while True:
            await asyncio.sleep(self.tick_interval)
            now = loop.time()
            try:
                self.advance(now - start, now - previous)
            except Exception:
                _LOG.exception(
                    "Simulation failed for %s (Unit ID %s)", self.name, self.unit_id
                )
                raise
            previous = now


class RuntimeContext:
    """Exact-address protocol boundary, isolated by Unit ID."""

    def __init__(self, devices: list[Device]) -> None:
        self.devices = {device.unit_id: device for device in devices}

    def device_ids(self) -> list[int]:
        return list(self.devices)

    async def async_getValues(
        self, device_id: int, func_code: int, address: int, count: int = 1
    ) -> Any:
        device = self.devices.get(device_id)
        if device is None:
            return ExcCodes.GATEWAY_NO_RESPONSE
        # PyModbus uses FC5/6 getValues internally to build the write echo;
        # these are not protocol read operations and must support writeOnly.
        if error := device.access(func_code, address, count, func_code in (5, 6)):
            return error
        table = FUNCTIONS[func_code]
        return [device.cells[table][item] for item in range(address, address + count)]

    async def async_setValues(
        self,
        device_id: int,
        func_code: int,
        address: int,
        values: list[int] | list[bool],
    ) -> Any:
        device = self.devices.get(device_id)
        if device is None:
            return ExcCodes.GATEWAY_NO_RESPONSE
        if error := device.access(func_code, address, len(values), True):
            return error
        table = FUNCTIONS[func_code]
        old = copy.deepcopy(device.cells)
        held = device.held.copy()
        try:
            full_mask = 1 if table in ("coil", "discrete_input") else 65535
            for offset, value in enumerate(values):
                current_address = address + offset
                allowed = device.write_masks[table].get(current_address, 0)
                current = int(device.cells[table][current_address])
                if (current ^ int(value)) & (full_mask ^ allowed):
                    raise ValueError("write changes read-only or unconfigured bits")
                device.cells[table][current_address] = value
            touched = {(table, item) for item in range(address, address + len(values))}
            changes = device.validate_cells(touched)
            device.held.update(changes)
            device.hook("on_write", changes)
            device.set_many(
                {
                    target: device.get(source)
                    for target, source in device.bindings.items()
                }
            )
        except Exception:
            device.cells = old
            device.held = held
            _LOG.exception("Write rejected by device %s", device.name)
            return ExcCodes.ILLEGAL_VALUE
        return None
