"""Bounded JSON loading and validation of the executable Modpoll subset."""

import json
import math
from dataclasses import dataclass
from pathlib import Path

from .acquisition import AcquisitionError, Group, parse_acquisition
from .validation import validate_standard
from .forms import validate_forms

CONTEXT = "https://top-maker.github.io/modpoll/vocab/wot-modbus#"
MODBUS_CONTEXT = "https://www.w3.org/2019/wot/modbus"
MAX_BYTES = 1048576
MAX_DEPTH = 64


@dataclass(frozen=True)
class Model:
    title: str
    kind: str
    groups: tuple[Group, ...]
    unit_id: int


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


def parse_model(document, *, kind=None, unit_id=None):
    if unit_id is not None and (type(unit_id) is not int or not 1 <= unit_id <= 254):
        raise AcquisitionError("unit_id: expected integer between 1 and 254")
    if not isinstance(document, dict):
        raise AcquisitionError("document: expected object")
    _check_depth(document)
    detected = _document_kind(document)
    if kind is None:
        kind = detected
    if kind != detected:
        raise AcquisitionError("document kind disagrees with tm:ThingModel declaration")
    validate_standard(document, kind=kind)
    contexts = document.get("@context", [])
    mappings = {}
    for context in contexts if isinstance(contexts, list) else []:
        if isinstance(context, dict):
            mappings.update(context)
    if mappings.get("modpoll") != CONTEXT or mappings.get("modv") != MODBUS_CONTEXT:
        raise AcquisitionError("@context: unsupported modpoll/modv vocabulary mapping")
    if (
        document.get("actions")
        or document.get("events")
        or document.get("links")
        or document.get("tm:extends")
    ):
        raise AcquisitionError(
            "actions/events/links/TM inheritance are unsupported in contract 0.1"
        )
    for key in document:
        if key.startswith("modpoll:") and key not in (
            "modpoll:version",
            "modpoll:acquisition",
        ):
            raise AcquisitionError(f"unsupported extension: {key}")
    if (
        document.get("forms")
        or document.get("uriVariables")
        or document.get("tm:optional")
    ):
        raise AcquisitionError(
            "root operations, URI templates and optional members are unsupported"
        )
    security = document.get("security", [])
    if isinstance(security, str):
        security = [security]
    definitions = document.get("securityDefinitions", {})
    if any(definitions.get(name, {}).get("scheme") != "nosec" for name in security):
        raise AcquisitionError("this Modbus configuration subset supports only nosec")
    for name, prop in document.get("properties", {}).items():
        if any(key.startswith(("modpoll:", "modv:")) for key in prop):
            raise AcquisitionError(
                f"/properties/{name}: executable metadata belongs in members/forms"
            )
    configured_id = document.get("modv:unitID", 1)
    if type(configured_id) is not int or not 1 <= configured_id <= 254:
        raise AcquisitionError("/modv:unitID: expected integer between 1 and 254")
    if unit_id is None:
        unit_id = configured_id
    groups = parse_acquisition(document)
    validate_forms(document, groups, unit_id, kind)
    if not document["title"].strip():
        raise AcquisitionError("/title: device name cannot be empty")
    return Model(document["title"], kind, groups, unit_id)


def loads_model(payload, *, source="<memory>", kind=None, unit_id=None):
    try:
        if (
            len(payload.encode("utf-8") if isinstance(payload, str) else payload)
            > MAX_BYTES
        ):
            raise AcquisitionError("configuration exceeds 1 MiB")
        document = json.loads(
            payload, object_pairs_hook=_pairs, parse_constant=_invalid_number
        )
        return parse_model(document, kind=kind, unit_id=unit_id)
    except (ValueError, TypeError, RecursionError) as exc:
        raise AcquisitionError(f"{source}: {exc}") from exc


def load_model(path, *, kind=None, unit_id=None):
    path = Path(path)
    try:
        with path.open("rb") as stream:
            payload = stream.read(MAX_BYTES + 1)
    except OSError as exc:
        raise AcquisitionError(f"{path}: {exc}") from exc
    return loads_model(payload, source=str(path), kind=kind, unit_id=unit_id)
