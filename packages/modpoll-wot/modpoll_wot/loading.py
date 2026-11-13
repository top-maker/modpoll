"""Bounded JSON loading and validation of the executable Modpoll subset."""

import json
import math
from dataclasses import dataclass
from pathlib import Path

from .acquisition import AcquisitionError, Group

MAX_BYTES = 1048576
MAX_DEPTH = 64


@dataclass(frozen=True)
class Model:
    title: str
    kind: str
    groups: tuple[Group, ...]
    unit_id: int
    endpoint: tuple[str, int] | None = None
    properties_json: str | None = None
    profile_version: str = "0.2"


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise AcquisitionError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _invalid_number(value):
    raise AcquisitionError(f"invalid JSON number: {value}")


def _check_depth(value, depth=0):
    if depth > MAX_DEPTH:
        raise AcquisitionError(f"JSON nesting exceeds {MAX_DEPTH}")
    if isinstance(value, float) and not math.isfinite(value):
        raise AcquisitionError("non-finite JSON number")
    if isinstance(value, dict):
        for item in value.values():
            _check_depth(item, depth + 1)
    elif isinstance(value, list):
        for item in value:
            _check_depth(item, depth + 1)


def _document_kind(document):
    """Select the schema from content; validation follows without fallback.

    The executable subset uses the fixed tm:ThingModel spelling. File names,
    URLs and arbitrary JSON-LD alias resolution do not participate in selection.
    """
    types = document.get("@type", [])
    if isinstance(types, str):
        types = [types]
    return "tm" if isinstance(types, list) and "tm:ThingModel" in types else "td"


def parse_model(
    document, *, kind=None, unit_id=None, host=None, port=None, parameters=None
):
    # Instantiation owns executable validation; kind is only a caller assertion.
    if kind is not None and (
        not isinstance(document, dict) or kind != _document_kind(document)
    ):
        raise AcquisitionError("document kind disagrees with tm:ThingModel declaration")
    from .profile import instantiate

    return instantiate(
        document, host=host, port=port, unit_id=unit_id, parameters=parameters
    )[0]


def _loads_document(payload):
    if (
        len(payload.encode("utf-8") if isinstance(payload, str) else payload)
        > MAX_BYTES
    ):
        raise AcquisitionError("configuration exceeds 1 MiB")
    document = json.loads(
        payload, object_pairs_hook=_pairs, parse_constant=_invalid_number
    )
    _check_depth(document)
    return document


def loads_model(payload, *, source="<memory>", kind=None, unit_id=None, **instance):
    try:
        return parse_model(
            _loads_document(payload), kind=kind, unit_id=unit_id, **instance
        )
    except (ValueError, TypeError, RecursionError) as exc:
        raise AcquisitionError(f"{source}: {exc}") from exc


def load_model(path, *, kind=None, unit_id=None, **instance):
    document = load_document(path)
    try:
        return parse_model(document, kind=kind, unit_id=unit_id, **instance)
    except (ValueError, TypeError, RecursionError) as exc:
        raise AcquisitionError(f"{path}: {exc}") from exc


def load_document(path):
    """Load bounded duplicate-free JSON for execution, validation and export."""
    path = Path(path)
    try:
        with path.open("rb") as stream:
            return _loads_document(stream.read(MAX_BYTES + 1))
    except (ValueError, TypeError, OSError, RecursionError) as exc:
        raise AcquisitionError(f"{path}: {exc}") from exc
