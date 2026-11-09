"""Point fingerprints and hardware verification reports."""

from decimal import Decimal
from functools import lru_cache
from hashlib import sha256
from importlib.resources import files
import json

from jsonschema import Draft202012Validator

from .acquisition import AcquisitionError
from .loading import _loads_document
from .profile import instantiate

FINGERPRINT_VERSION = "pf1"
MODEL_FINGERPRINT_VERSION = "mf1"
REPORT_VERSION = 2
# Form fields that decide which bytes are read and how they become a value.
OPTIONAL_FIELDS = (
    "modpoll:codec",
    "modpoll:bit",
    "modpoll:multiplier",
    "modpoll:bitPacking",
)


class ReportError(ValueError):
    """A verification report is invalid or disagrees with its model."""


def _document(model):
    if isinstance(model, (bytes, bytearray)):
        return _loads_document(bytes(model))
    return model


def _decimal_string(value):
    number = Decimal(str(value)).normalize()
    return "0" if number == 0 else format(number, "f")


def _readable_form(prop):
    for form in prop["forms"]:
        ops = form["op"] if isinstance(form["op"], list) else [form["op"]]
        if "readproperty" in ops:
            return form
    return None


def canonical_point(prop):
    """Return the canonical read mapping of one effective property, or None."""
    form = _readable_form(prop)
    if form is None:
        return None
    raw = form["modv:type"]
    point = {
        "type": prop["type"],
        "modv:entity": form["modv:entity"],
        "modv:address": form["modv:address"],
        "modv:quantity": form["modv:quantity"],
        "modv:type": raw,
        "modv:mostSignificantByte": form.get("modv:mostSignificantByte", True),
        "modv:mostSignificantWord": form.get("modv:mostSignificantWord", True),
    }
    for key in OPTIONAL_FIELDS:
        if key in form:
            point[key] = form[key]
    if "modpoll:multiplier" in point:
        point["modpoll:multiplier"] = _decimal_string(point["modpoll:multiplier"])
    if raw == "xsd:string":
        bits = form["modv:entity"] in ("Coil", "DiscreteInput")
        quantity = form["modv:quantity"]
        point["modpoll:byteLength"] = form.get(
            "modpoll:byteLength", quantity // 8 if bits else quantity * 2
        )
    return point


def fingerprint(point):
    """Hash a canonical point mapping into a versioned fingerprint."""
    encoded = json.dumps(
        point, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return f"{FINGERPRINT_VERSION}:{sha256(encoded).hexdigest()}"


def point_fingerprints(model) -> dict[str, str]:
    """Return fingerprints of the readable points of a TM or TD.

    ``model`` is a parsed document or its exact bytes. Instance data such as
    the endpoint, Unit ID, property names and descriptions do not contribute.
    """
    try:
        _, effective = instantiate(_document(model))
    except (TypeError, RecursionError) as exc:
        raise AcquisitionError(str(exc)) from exc
    result = {}
    for name, prop in effective["properties"].items():
        point = canonical_point(prop)
        if point is not None:
            result[name] = fingerprint(point)
    return result


def combine_fingerprints(fingerprints) -> str:
    """Hash a collection of point fingerprints into a model fingerprint."""
    encoded = json.dumps(sorted(set(fingerprints)), separators=(",", ":")).encode()
    return f"{MODEL_FINGERPRINT_VERSION}:{sha256(encoded).hexdigest()}"


def model_fingerprint(model) -> str:
    """Return the fingerprint of the set of readable point mappings of a model.

    Cosmetic edits, renames and instance data keep the fingerprint, so an
    unmodified fork shares it with its parent.
    """
    return combine_fingerprints(point_fingerprints(model).values())


@lru_cache(maxsize=1)
def _report_validator():
    schema = json.loads(
        files("modpoll_wot")
        .joinpath("schemas", "verification-report-2.json")
        .read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def validate_report(report, *, model: bytes | None = None):
    """Validate a verification report, optionally against its exact TM bytes."""
    error = next(_report_validator().iter_errors(report), None)
    if error is not None:
        path = "/" + "/".join(
            str(p).replace("~", "~0").replace("/", "~1") for p in error.absolute_path
        )
        raise ReportError(f"{path}: {error.message}")
    names = [point["property"] for point in report["points"]]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise ReportError(f"/points: duplicate properties {duplicates}")
    if model is None:
        return
    if sha256(model).hexdigest() != report["model"]["sha256"]:
        raise ReportError("/model/sha256: does not match the model bytes")
    expected = point_fingerprints(model)
    if combine_fingerprints(expected.values()) != report["model"]["fingerprint"]:
        raise ReportError("/model/fingerprint: does not match the model")
    for index, point in enumerate(report["points"]):
        actual = expected.get(point["property"])
        if actual is None:
            raise ReportError(
                f"/points/{index}: no readable property {point['property']}"
            )
        if actual != point["fingerprint"]:
            raise ReportError(f"/points/{index}/fingerprint: does not match the model")
