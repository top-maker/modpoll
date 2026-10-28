"""Isolated standards-first experiment; not part of the released contract.

Run with python -m modpoll_wot.pilot --config PATH --host HOST --output PATH.
Neither the application's default loader nor the package exports use this API.
"""

import argparse
import copy
import ipaddress
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit, parse_qs

from jsonschema import Draft7Validator

from .acquisition import AcquisitionError, type_width
from .loading import (
    MAX_BYTES,
    _check_depth,
    _document_kind,
    _invalid_number,
    _pairs,
    parse_model,
)
from .validation import validate_standard

VERSION = "0.2-pilot"
TYPES = {
    "xsd:unsignedShort": "uint16",
    "xsd:short": "int16",
    "xsd:unsignedInt": "uint32",
    "xsd:int": "int32",
    "xsd:unsignedLong": "uint64",
    "xsd:long": "int64",
    "xsd:float": "float32",
    "xsd:double": "float64",
}
GROUP_SCHEMA = {
    "type": "array",
    "minItems": 1,
    "items": {
        "type": "object",
        "additionalProperties": False,
        "required": ["modv:entity", "modv:address", "modv:quantity", "modpoll:members"],
        "properties": {
            "modv:entity": {"enum": ["InputRegister", "HoldingRegister"]},
            "modv:address": {"type": "integer", "minimum": 0, "maximum": 65535},
            "modv:quantity": {"type": "integer", "minimum": 1, "maximum": 125},
            "modpoll:members": {
                "type": "array",
                "minItems": 1,
                "uniqueItems": True,
                "items": {"type": "string"},
            },
        },
    },
}
FORM_KEYS = {
    "href",
    "op",
    "contentType",
    "modv:entity",
    "modv:address",
    "modv:quantity",
    "modv:type",
    "modv:mostSignificantByte",
    "modv:mostSignificantWord",
}


def _check(schema, value, path):
    error = next(Draft7Validator(schema).iter_errors(value), None)
    if error:
        raise AcquisitionError(f"{path}: {error.message}")


def _authority(host, port):
    if type(port) is not int or not 1 <= port <= 65535:
        raise AcquisitionError("port: expected integer between 1 and 65535")
    if not isinstance(host, str) or not host:
        raise AcquisitionError("host: required for a TM")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        if len(host) > 253 or not all(
            re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label)
            for label in host.split(".")
        ):
            raise AcquisitionError("host: expected an IP address or DNS hostname")
    else:
        if address.is_unspecified or address.is_multicast:
            raise AcquisitionError(
                "host: a listening wildcard/multicast is not an endpoint"
            )
        if address.version == 6:
            host = f"[{host}]"
    return f"{host}:{port}"


def _td_endpoint(form, path):
    try:
        url = urlsplit(form["href"])
        parts = url.path.strip("/").split("/")
        unit, address = map(int, parts)
        query = parse_qs(url.query, strict_parsing=True, keep_blank_values=True)
        if set(query) - {"quantity"} or len(query.get("quantity", [])) > 1:
            raise ValueError()
        quantity = int(query.get("quantity", ["1"])[0])
        if url.scheme != "modbus+tcp" or url.username or url.password or url.fragment:
            raise ValueError()
        authority = _authority(url.hostname, 502 if url.port is None else url.port)
        if not 1 <= unit <= 254:
            raise ValueError()
    except (KeyError, TypeError, ValueError) as exc:
        raise AcquisitionError(f"{path}: invalid concrete Modbus TCP href") from exc
    return authority, unit, address, quantity


def _reject_placeholders(value):
    if isinstance(value, str) and "{{" in value:
        raise AcquisitionError("TM placeholders are unsupported in this pilot")
    if isinstance(value, dict):
        for item in value.values():
            _reject_placeholders(item)
    elif isinstance(value, list):
        for item in value:
            _reject_placeholders(item)


def compile_model(document, *, host=None, port=None, unit_id=None):
    """Return (execution model, concrete TD) without mutating the source.

    TM accepts TCP instance arguments. TD uses its declared endpoint; overrides
    are deliberately rejected until their semantics are designed and tested.
    Only one Form per numeric register property is supported in this pilot.
    """
    if not isinstance(document, dict):
        raise AcquisitionError("document: expected object")
    _check_depth(document)
    _reject_placeholders(document)
    if any(key.startswith("modv:") for key in document):
        raise AcquisitionError("root Modbus defaults are unsupported in the pilot")
    kind = _document_kind(document)
    validate_standard(document, kind=kind)
    if document.get("modpoll:version") != VERSION:
        raise AcquisitionError(f"pilot requires modpoll:version {VERSION}")
    _check(GROUP_SCHEMA, document.get("modpoll:acquisition"), "/modpoll:acquisition")
    if kind == "tm":
        authority = _authority(host, 502 if port is None else port)
        unit = 1 if unit_id is None else unit_id
        if type(unit) is not int or not 1 <= unit <= 254:
            raise AcquisitionError("unit_id: expected integer between 1 and 254")
    else:
        if any(value is not None for value in (host, port, unit_id)):
            raise AcquisitionError("TD instance overrides are unsupported in the pilot")
        authority = unit = None
    td = copy.deepcopy(document)
    normalized = copy.deepcopy(document)
    contexts = td.get("@context", [])
    mappings = {}
    for context in contexts if isinstance(contexts, list) else []:
        if isinstance(context, dict):
            mappings.update(context)
    if mappings.get("xsd") != "http://www.w3.org/2001/XMLSchema#":
        raise AcquisitionError("@context: unsupported xsd vocabulary mapping")
    metadata = {}
    for name, prop in td.get("properties", {}).items():
        path = f"/properties/{name}/forms"
        forms = prop.get("forms", [])
        if (
            not isinstance(forms, list)
            or len(forms) != 1
            or not isinstance(forms[0], dict)
        ):
            raise AcquisitionError(
                f"{path}: pilot requires exactly one unambiguous Form"
            )
        form = forms[0]
        if set(form) - FORM_KEYS:
            raise AcquisitionError(
                f"{path}: unsupported Form terms (including transforms)"
            )
        dtype = TYPES.get(form.get("modv:type"))
        if dtype is None:
            raise AcquisitionError(f"{path}: unsupported or missing modv:type")
        entity = form.get("modv:entity")
        if entity not in ("InputRegister", "HoldingRegister"):
            raise AcquisitionError(f"{path}: only register entities are supported")
        width = type_width(dtype)
        byte_order = []
        for key in ("modv:mostSignificantByte", "modv:mostSignificantWord"):
            value = form.get(key, True)
            if type(value) is not bool:
                raise AcquisitionError(f"{path}/{key}: expected boolean")
            byte_order.append(value)
        if kind == "td":
            remote, actual_unit, address, count = _td_endpoint(form, path)
            if authority is not None and (authority, unit) != (remote, actual_unit):
                raise AcquisitionError(
                    f"{path}: multiple endpoints/Unit IDs are unsupported"
                )
            authority, unit = remote, actual_unit
            for key, value in (("modv:address", address), ("modv:quantity", count)):
                if key in form and (type(form[key]) is not int or form[key] != value):
                    raise AcquisitionError(f"{path}: href disagrees with {key}")
        else:
            if "href" in form:
                raise AcquisitionError(f"{path}: pilot TM Forms must omit href")
            address, count = form.get("modv:address"), form.get("modv:quantity", 1)
        if type(address) is not int or not 0 <= address <= 65535:
            raise AcquisitionError(f"{path}: invalid modv:address")
        if type(count) is not int or count != width or address + count > 65536:
            raise AcquisitionError(
                f"{path}: quantity must match modv:type width and address range"
            )
        form["href"] = f"modbus+tcp://{authority}/{unit}/{address}?quantity={count}"
        metadata[name] = (entity, address, dtype, tuple(byte_order))
    normalized["properties"] = copy.deepcopy(td.get("properties", {}))
    groups = []
    for index, group in enumerate(td["modpoll:acquisition"]):
        members, order = [], None
        for name in group["modpoll:members"]:
            if name not in metadata:
                raise AcquisitionError(
                    f"/modpoll:acquisition/{index}: unknown property {name}"
                )
            entity, address, dtype, endian = metadata[name]
            if entity != group["modv:entity"]:
                raise AcquisitionError(
                    f"/modpoll:acquisition/{index}: member entity disagrees"
                )
            if order is not None and endian != order:
                raise AcquisitionError(
                    f"/modpoll:acquisition/{index}: mixed byte orders unsupported in pilot"
                )
            order = endian
            members.append(
                {
                    "modpoll:property": name,
                    "modpoll:offset": address - group["modv:address"],
                    "modpoll:dataType": dtype,
                }
            )
        groups.append(
            {
                **group,
                "modpoll:members": members,
                "modv:mostSignificantByte": order[0],
                "modv:mostSignificantWord": order[1],
            }
        )
    # Reuse the released execution checks through a private compatibility adapter;
    # the source and exported TD never contain these duplicated codec fields.
    normalized["modpoll:version"] = "0.1"
    normalized["modpoll:acquisition"] = groups
    model = parse_model(normalized, unit_id=unit)
    types = td.get("@type", [])
    if isinstance(types, str):
        types = [types]
    types = [value for value in types if value != "tm:ThingModel"]
    td.pop("@type", None)
    if types:
        td["@type"] = types
    if "security" not in td:
        td.setdefault("securityDefinitions", {})["pilot_nosec"] = {"scheme": "nosec"}
        td["security"] = "pilot_nosec"
    validate_standard(td, kind="td")
    return model, td


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--host")
    parser.add_argument("--port", type=int)
    parser.add_argument("--unit-id", type=int)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        with Path(args.config).open("rb") as stream:
            payload = stream.read(MAX_BYTES + 1)
        if len(payload) > MAX_BYTES:
            raise AcquisitionError("configuration exceeds 1 MiB")
        document = json.loads(
            payload, object_pairs_hook=_pairs, parse_constant=_invalid_number
        )
        _, td = compile_model(
            document, host=args.host, port=args.port, unit_id=args.unit_id
        )
        with Path(args.output).open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(td, indent=2, ensure_ascii=False) + "\n")
    except (ValueError, OSError, RecursionError) as exc:
        print(f"{args.config}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
