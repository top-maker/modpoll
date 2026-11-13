"""Simulation data: declarative device values for simulators.

A simulation data document has `"version": "1"` and follows
schemas/simulation-data-1.json. A Modpoll `--export` snapshot, which has no
`version`, is also accepted: the entry for one device becomes its static
`initial` values. The two shapes are told apart by the `version` key alone.
"""

from dataclasses import dataclass
from fractions import Fraction
from functools import lru_cache
from importlib.resources import files
import json
import math

from jsonschema import Draft202012Validator

DATA_VERSION = "1"
SNAPSHOT_TIMESTAMP = "timestamp"


class DataError(ValueError):
    """Simulation data or a snapshot is invalid."""


@dataclass(frozen=True)
class SimulationData:
    """Simulation data in document form, and where it came from."""

    data: dict
    source: str  # "data" or "snapshot"
    unread: tuple[str, ...] = ()  # snapshot points Modpoll could not read


@lru_cache(maxsize=1)
def _validator():
    schema = json.loads(
        files("modpoll_wot")
        .joinpath("schemas", "simulation-data-1.json")
        .read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _validate(document):
    error = next(_validator().iter_errors(document), None)
    if error is not None:
        path = "/" + "/".join(str(part) for part in error.absolute_path)
        raise DataError(f"simulation data {path}: {error.message}")


def _snapshot_entry(snapshot, title):
    if not snapshot or not all(isinstance(entry, dict) for entry in snapshot.values()):
        raise DataError(
            "a snapshot maps device titles to point values; "
            'simulation data needs "version": "1"'
        )
    if title in snapshot:
        return snapshot[title]
    if len(snapshot) == 1:
        return next(iter(snapshot.values()))
    names = ", ".join(sorted(snapshot))
    raise DataError(f"snapshot holds devices {names}; none is titled {title!r}")


def load_simulation_data(document, *, title=None, properties=None):
    """Return a SimulationData from a data document or a Modpoll snapshot.

    `title` selects a device from a snapshot with several devices. When
    `properties` (the model's property names) is given, every referenced name
    must be one of them, and a snapshot `timestamp` entry is a point only if the
    model has a property of that name.
    """
    if not isinstance(document, dict):
        raise DataError("simulation data must be a JSON object")
    if "version" in document:
        data, source, unread = document, "data", ()
    else:
        entry = _snapshot_entry(document, title)
        values = {
            name: value
            for name, value in entry.items()
            if name != SNAPSHOT_TIMESTAMP
            or (properties is not None and name in properties)
        }
        unread = tuple(sorted(name for name, value in values.items() if value is None))
        initial = {name: value for name, value in values.items() if value is not None}
        data, source = {"version": DATA_VERSION, "initial": initial}, "snapshot"
    _validate(data)
    if properties is not None:
        names = set(properties)
        bindings = data.get("bindings", {})
        referenced = (
            data.get("initial", {}).keys()
            | data.get("generators", {}).keys()
            | bindings.keys()
            | set(bindings.values())
        )
        unknown = sorted(referenced - names)
        if unknown:
            raise DataError(f"simulation data names unknown properties: {unknown}")
    return SimulationData(data=data, source=source, unread=unread)


def scaled_raw(value, multiplier):
    """Return the raw integer behind an engineering value and its multiplier.

    A value is accepted when it is the raw integer times the multiplier exactly
    in decimal (230.1 with 0.1), or exactly the float Modpoll computes as
    float(raw) * float(multiplier) (230.10000000000002 with 0.1). Anything else
    raises DataError; there is no tolerance threshold.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DataError(f"expected a number, got {value!r}")
    if isinstance(value, float) and not math.isfinite(value):
        raise DataError(f"expected a finite number, got {value!r}")
    factor = Fraction(str(multiplier))
    exact = Fraction(str(value))
    if factor == 0:
        if exact != 0:
            raise DataError("a zero multiplier only represents zero")
        return 0
    quotient = exact / factor
    raw = round(quotient)
    if quotient == raw or float(raw) * float(factor) == value:
        return raw
    raise DataError(f"{value!r} is not an integer multiple of {multiplier}")
