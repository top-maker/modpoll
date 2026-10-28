"""Offline JSON Schema validation against bundled, immutable schemas."""

import json
from functools import lru_cache
from importlib.resources import files

from jsonschema import Draft7Validator
from referencing import Registry, Resource

from .acquisition import AcquisitionError


class ModelValidationError(AcquisitionError):
    """A document does not match its selected schema."""


def _no_remote(uri):
    raise ModelValidationError(f"remote schema resolution is disabled: {uri}")


@lru_cache(maxsize=5)
def _validator(kind):
    names = {
        "tm": "tm-1.1.json",
        "td": "td-1.1.json",
        "acquisition": "acquisition-0.1.json",
        "acquisition-0.2": "acquisition-0.2.json",
        "modbus": "modbus-binding.json",
    }
    if kind not in names:
        raise ValueError("kind must be 'tm' or 'td'")
    schema = json.loads(
        files("modpoll_wot")
        .joinpath("schemas", names[kind])
        .read_text(encoding="utf-8")
    )
    Draft7Validator.check_schema(schema)
    registry = Registry(retrieve=_no_remote)
    if kind == "modbus":
        td = json.loads(
            files("modpoll_wot")
            .joinpath("schemas", "td-1.1.json")
            .read_text(encoding="utf-8")
        )
        registry = registry.with_resource(
            "https://www.w3.org/2022/wot/td-schema/v1.1", Resource.from_contents(td)
        )
    return Draft7Validator(schema, registry=registry)


def _validate(document, kind):
    error = next(_validator(kind).iter_errors(document), None)
    if error is not None:
        path = "/" + "/".join(
            str(p).replace("~", "~0").replace("/", "~1") for p in error.absolute_path
        )
        raise ModelValidationError(f"{path}: {error.message}")


def validate_standard(document, *, kind):
    """Validate WoT standard structure, not device or acquisition semantics."""
    if kind not in ("tm", "td"):
        raise ValueError("kind must be 'tm' or 'td'")
    _validate(document, kind)


def validate_extension(document, *, version="0.1"):
    if version not in ("0.1", "0.2"):
        raise ValueError("unsupported executable profile version")
    _validate(document, "acquisition" if version == "0.1" else "acquisition-0.2")


def validate_modbus(document):
    """Check the pinned official binding schema offline, in addition to TD 1.1."""
    _validate(document, "modbus")
