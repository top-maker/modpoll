"""Local deployment and scenario contracts for a single listener."""

import math
from pathlib import Path
from typing import Any

from jsonschema import Draft7Validator  # type: ignore[import-untyped]
from modpoll_wot.loading import load_document  # type: ignore[import-untyped]

from .sources import local_path


def obj(properties: dict, required: tuple = ()) -> dict:
    return {
        "type": "object",
        "properties": properties,
        "required": list(required),
        "additionalProperties": False,
    }


STRING = {"type": "string", "minLength": 1}
NUMBER = {"type": "number"}
POSITIVE = {"type": "number", "exclusiveMinimum": 0}
INITIAL = {"type": "object"}
GENERATOR = {
    "oneOf": [
        obj({"kind": {"const": "constant"}, "value": {}}, ("kind", "value")),
        obj(
            {
                "kind": {"const": "sine"},
                "center": NUMBER,
                "amplitude": {"type": "number", "minimum": 0},
                "period": POSITIVE,
            },
            ("kind", "center", "amplitude", "period"),
        ),
        obj(
            {
                "kind": {"const": "ramp"},
                "start": NUMBER,
                "rate": NUMBER,
                "minimum": NUMBER,
                "maximum": NUMBER,
            },
            ("kind", "start", "rate", "minimum", "maximum"),
        ),
        obj(
            {"kind": {"const": "noise"}, "minimum": NUMBER, "maximum": NUMBER},
            ("kind", "minimum", "maximum"),
        ),
    ]
}
SCENARIO = obj(
    {
        "version": {"const": "1"},
        "initial": INITIAL,
        "seed": {"type": "integer"},
        "tick": POSITIVE,
        "generators": {"type": "object", "additionalProperties": GENERATOR},
        "bindings": {"type": "object", "additionalProperties": STRING},
        "script": STRING,
        "parameters": INITIAL,
        "writePolicy": {"enum": ["hold", "overwrite"]},
    },
    ("version",),
)


def document(path: str, schema: dict) -> dict:
    source = Path(local_path(Path.cwd(), path))
    value = load_document(source)
    errors = sorted(
        Draft7Validator(schema).iter_errors(value), key=lambda error: str(error.path)
    )
    if errors:
        error = errors[0]
        raise ValueError(f"{source}: {'/'.join(map(str, error.path))}: {error.message}")
    return value  # type: ignore[no-any-return]


def apply_scenario(args: Any) -> None:
    device = args.runtime
    spec = getattr(args, "scenario_spec", None)
    if spec is None:
        spec = document(args.scenario, SCENARIO) if args.scenario else {}
    device.tick_interval = spec.get("tick", 1.0)
    if not math.isfinite(device.tick_interval) or device.tick_interval < 0.001:
        raise ValueError("scenario tick must be finite and at least 0.001 seconds")
    device.random.seed(spec.get("seed", 0))
    device.parameters = spec.get("parameters", {})
    device.generators = spec.get("generators", {})
    device.bindings = spec.get("bindings", {})
    device.write_policy = spec.get("writePolicy", "hold")
    targets = device.generators.keys() | device.bindings.keys()
    if (
        targets - device.members.keys()
        or set(device.bindings.values()) - device.members.keys()
    ):
        raise ValueError(f"{device.name}: scenario references unknown properties")
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
    # CLI/deployment initial values take precedence over scenario defaults.
    from modpoll_wot import parse_parameters  # type: ignore[import-untyped]

    if args.initial_file:
        initial.update(load_document(args.initial_file))
    initial.update(parse_parameters(args.initial))
    device.set_many(initial)
    script = args.script
    if script and spec.get("script"):
        raise ValueError("choose a script in either the scenario or device/CLI")
    if not script and spec.get("script"):
        script = local_path(Path(args.scenario).resolve().parent, spec["script"])
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
        origins[name] = "scenario initial"
    for name in initial:
        if (
            name not in spec.get("initial", {})
            or name in parse_parameters(args.initial)
            or args.initial_file
        ):
            origins[name] = "instance initial"
    if script:
        for name in origins:
            origins[name] = "local script/initialization"
    for name in device.generators:
        origins[name] = "scenario generator"
    for name in device.bindings:
        origins[name] = "scenario binding"
    args.model_initialization["values"] = {
        name: device.get(name) for name in device.members
    }


def configure_devices(args: Any) -> list:
    """Configure a single --config device."""
    from .wot import configure

    sim = configure(args)
    apply_scenario(args)
    args.runtimes = [args.runtime]
    return [sim]
