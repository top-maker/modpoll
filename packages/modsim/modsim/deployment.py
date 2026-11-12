"""Simulation data and behavior for a single configured device."""

import logging
import math
from pathlib import Path
from typing import Any

from modpoll_wot import load_simulation_data  # type: ignore[import-untyped]
from modpoll_wot.loading import load_document  # type: ignore[import-untyped]

from .sources import is_remote, local_path, remote_document

logger = logging.getLogger(__name__)


def obj(properties: dict, required: tuple = ()) -> dict:
    return {
        "type": "object",
        "properties": properties,
        "required": list(required),
        "additionalProperties": False,
    }


STRING = {"type": "string", "minLength": 1}


def data_document(source: str) -> dict:
    """Load simulation data, or a modpoll --export snapshot, from a path or HTTPS URL."""
    if is_remote(source):
        return remote_document(source)
    return load_document(Path(local_path(Path.cwd(), source)))  # type: ignore[no-any-return]


def resolve_data(document: dict, device: Any, title: str) -> dict:
    """Check simulation data or a snapshot against the device's properties."""
    loaded = load_simulation_data(
        document, title=title, properties=device.members.keys()
    )
    if loaded.unread:
        logger.warning(
            "%s: snapshot points without a value keep their defaults: %s",
            title,
            ", ".join(loaded.unread),
        )
    return loaded.data  # type: ignore[no-any-return]


def apply_data(args: Any) -> None:
    """Apply simulation data, CLI initial values and local behavior to a device."""
    device = args.runtime
    title = args.model_initialization["title"]
    spec = getattr(args, "data_spec", None)
    if spec is None:
        spec = (
            resolve_data(data_document(args.data), device, title) if args.data else {}
        )
    device.tick_interval = spec.get("tick", 1.0)
    if not math.isfinite(device.tick_interval) or device.tick_interval < 0.001:
        raise ValueError("data tick must be finite and at least 0.001 seconds")
    device.random.seed(spec.get("seed", 0))
    device.parameters = getattr(args, "script_parameters", None) or {}
    device.generators = spec.get("generators", {})
    device.bindings = spec.get("bindings", {})
    device.write_policy = spec.get("writePolicy", "hold")
    targets = device.generators.keys() | device.bindings.keys()
    if (
        targets - device.members.keys()
        or set(device.bindings.values()) - device.members.keys()
    ):
        raise ValueError(
            f"{device.name}: simulation data references unknown properties"
        )
    if device.generators.keys() & device.bindings.keys():
        raise ValueError("a property cannot have both a generator and a binding")
    if device.bindings.keys() & set(device.bindings.values()):
        raise ValueError("binding chains/cycles are unsupported; use a script")
    for name, rule in device.generators.items():
        if rule["kind"] in ("ramp", "noise") and rule["minimum"] > rule["maximum"]:
            raise ValueError(f"{name}: generator minimum exceeds maximum")
    # Validate full declared generator envelopes before opening the listener.
    import copy

    saved = copy.deepcopy(device.cells)
    try:
        for name, rule in device.generators.items():
            if rule["kind"] == "constant":
                candidates = [rule["value"]]
            elif rule["kind"] == "sine":
                candidates = [
                    rule["center"] - rule["amplitude"],
                    rule["center"] + rule["amplitude"],
                ]
            else:
                candidates = [rule["minimum"], rule["maximum"]]
            if (
                device.schemas[name].get("type") == "boolean"
                and rule["kind"] != "constant"
            ):
                raise ValueError(f"{name}: boolean generators require constant values")
            for value in candidates:
                if (
                    device.schemas[name].get("type") == "integer"
                    and type(value) is not bool
                ):
                    value = round(value)
                device.set(name, value)
    finally:
        device.cells = saved
    initial = dict(spec.get("initial", {}))
    # CLI initial values take precedence over simulation data.
    from modpoll_wot import parse_parameters

    initial.update(parse_parameters(args.initial))
    device.set_many(initial)
    script = args.script
    if script:
        if not args.allow_scripts:
            raise ValueError("Python behavior scripts require --allow-scripts")
        device.load_script(
            local_path(Path.cwd(), script), getattr(args, "script_source", None)
        )
    device.hook("initialize")
    device.advance(0.0, 0.0)
    origins = args.model_initialization["origins"]
    for name in spec.get("initial", {}):
        origins[name] = "data initial"
    for name in parse_parameters(args.initial):
        origins[name] = "instance initial"
    if script:
        for name in origins:
            origins[name] = "local script/initialization"
    for name in device.generators:
        origins[name] = "data generator"
    for name in device.bindings:
        origins[name] = "data binding"
    args.model_initialization["values"] = {
        name: device.get(name) for name in device.members
    }


def configure_devices(args: Any) -> list:
    """Configure a single --config device."""
    from .wot import configure

    sim = configure(args)
    apply_data(args)
    args.runtimes = [args.runtime]
    return [sim]
