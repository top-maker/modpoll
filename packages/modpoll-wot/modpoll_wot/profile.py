"""Contract 0.2 candidate: standard Forms, explicit blocks and TD instantiation."""

import copy
from dataclasses import replace
import json
import re

from .acquisition import AcquisitionError, Group, type_width
from .endpoint import _authority, _td_endpoint
from .loading import _check_depth, _document_kind, parse_model
from .validation import validate_standard, validate_extension, validate_modbus

VERSION = "0.2"
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
PLACEHOLDER = re.compile(r"\{\{([ -~]+?)\}\}")


def parse_parameters(items):
    """Parse typed CLI bindings once for all consumers, rejecting duplicates."""
    from .loading import _pairs, _invalid_number

    result = {}
    for item in items:
        try:
            key, value = item.split("=", 1)
            if not key or key in result:
                raise AcquisitionError("empty or duplicate parameter name")
            result[key] = json.loads(
                value, object_pairs_hook=_pairs, parse_constant=_invalid_number
            )
        except (TypeError, ValueError) as exc:
            raise AcquisitionError(f"invalid TM parameter {item!r}: {exc}") from exc
    _check_depth(result)
    return result


def _substitute(value, parameters, used):
    if isinstance(value, dict):
        return {key: _substitute(item, parameters, used) for key, item in value.items()}
    if isinstance(value, list):
        return [_substitute(item, parameters, used) for item in value]
    if not isinstance(value, str):
        return value
    matches = list(PLACEHOLDER.finditer(value))
    if not matches:
        if "{{" in value or "}}" in value:
            raise AcquisitionError("malformed TM placeholder")
        return value
    for match in matches:
        name = match[1]
        if name not in parameters:
            raise AcquisitionError(f"unbound TM placeholder: {name}")
        used.add(name)
    if len(matches) == 1 and matches[0].span() == (0, len(value)):
        return copy.deepcopy(parameters[matches[0][1]])

    def embedded(match):
        result = parameters[match[1]]
        if not isinstance(result, (str, int, float)) or isinstance(result, bool):
            raise AcquisitionError(
                "embedded placeholders require string/numeric parameters"
            )
        return str(result)

    return PLACEHOLDER.sub(embedded, value)


def _codec(form, prop, count, bits, path):
    raw, special = form.get("modv:type"), form.get("modpoll:codec")
    scalar = False
    if special is not None:
        if (
            raw != "xsd:hexBinary"
            or special not in ("float16", "bool", "bool8", "bool16")
            or bits
        ):
            raise AcquisitionError(f"{path}: unsupported or redundant codec")
        dtype = special
    elif "modpoll:bit" in form:
        if raw != "xsd:unsignedShort" or bits:
            raise AcquisitionError(
                f"{path}: bit extraction requires a register unsignedShort"
            )
        if type(form["modpoll:bit"]) is not int:
            raise AcquisitionError(f"{path}: bit index must be an integer")
        dtype = "bool"
    elif raw == "xsd:boolean":
        if prop.get("type") not in ("boolean", "array") or (
            not bits and prop.get("type") != "boolean"
        ):
            raise AcquisitionError(f"{path}: invalid boolean property")
        dtype, scalar = ("bool" if bits else "uint16"), prop.get("type") == "boolean"
        if scalar and count != 1:
            raise AcquisitionError(f"{path}: scalar boolean requires quantity 1")
    elif raw == "xsd:string":
        capacity = form.get("modpoll:byteLength", count // 8 if bits else count * 2)
        if type(capacity) is not int or not 1 <= capacity <= 9999:
            raise AcquisitionError(f"{path}: invalid string byteLength")
        dtype = f"string{capacity}"
    elif raw in TYPES:
        dtype = TYPES[raw]
    else:
        raise AcquisitionError(f"{path}: unsupported or missing raw type")
    if "modpoll:byteLength" in form and raw != "xsd:string":
        raise AcquisitionError(f"{path}: byteLength only applies to strings")
    if bits and raw != "xsd:boolean":
        if form.get("modpoll:bitPacking") != "legacy-msb":
            raise AcquisitionError(
                f"{path}: packed bit payload requires explicit legacy-msb packing"
            )
    elif "modpoll:bitPacking" in form:
        raise AcquisitionError(
            f"{path}: bitPacking is only for non-boolean bit-table payloads"
        )
    if raw == "xsd:boolean" and "modpoll:multiplier" in form:
        raise AcquisitionError(f"{path}: booleans cannot be multiplied")
    expected = (
        count
        if bits and raw == "xsd:boolean"
        else type_width(dtype, bit_table=True) * 8 if bits else type_width(dtype)
    )
    if count != expected:
        raise AcquisitionError(f"{path}: quantity disagrees with raw codec width")
    return dtype, scalar


def _validate_media(form, prop, dtype, scalar, bits, endian, path):
    """Accept explicit binary parameters only when they match the raw mapping."""
    media = form.get("contentType", "application/octet-stream")
    if media == "application/octet-stream":
        return
    if not isinstance(media, str):
        raise AcquisitionError(f"{path}: invalid contentType")
    parts = [part.strip() for part in media.split(";")]
    if parts[0] != "application/octet-stream":
        raise AcquisitionError(
            f"{path}: source media type must be application/octet-stream"
        )
    native_bit = bits and scalar and form.get("modv:type") == "xsd:boolean"
    if (
        prop.get("type") == "array"
        or any(
            key in form
            for key in ("modpoll:codec", "modpoll:bit", "modpoll:multiplier")
        )
        or (bits and not native_bit)
        or (not native_bit and dtype not in TYPES.values())
    ):
        raise AcquisitionError(
            f"{path}: binary media parameters require native scalar values"
        )
    length = 1 if native_bit else type_width(dtype) * 2
    order = {
        (True, True): "BIG_ENDIAN",
        (False, False): "LITTLE_ENDIAN",
        (False, True): "BIG_ENDIAN_BYTE_SWAP",
        (True, False): "LITTLE_ENDIAN_BYTE_SWAP",
    }[endian]
    if length == 2:
        order = "BIG_ENDIAN" if endian[0] else "LITTLE_ENDIAN"
    expected = {
        "length": str(length),
        "signed": "false" if native_bit or dtype.startswith("uint") else "true",
        "byteSeq": order,
    }
    seen = set()
    for part in parts[1:]:
        key, sep, value = part.partition("=")
        key, value = key.strip(), value.strip()
        if not sep or key in seen or key not in expected or value != expected[key]:
            raise AcquisitionError(
                f"{path}: conflicting or unsupported binary media parameter: {part}"
            )
        seen.add(key)


def instantiate(document, *, host=None, port=None, unit_id=None, parameters=None):
    """Return a validated execution Model and effective TD, preserving the input.

    Explicit instance arguments override a validated TD endpoint. Without them,
    TD endpoints are authoritative. TM defaults are TCP port 502 / Unit ID 1;
    an unbound TM may execute over a CLI-selected serial/UDP transport, but cannot
    be exported as a concrete TCP TD without a host.
    """
    if not isinstance(document, dict):
        raise AcquisitionError("document: expected object")
    _check_depth(document)
    kind = _document_kind(document)
    if parameters and kind != "tm":
        raise AcquisitionError("parameters are only valid for TM input")
    used = set()
    explicit = dict(parameters or {})
    bindings = {"PORT": 502, "UNIT_ID": 1, **explicit}
    if host is not None:
        bindings["HOST"] = host
        bindings["AUTHORITY"] = _authority(host, 502 if port is None else port)
    if port is not None:
        bindings["PORT"] = port
    if unit_id is not None:
        bindings["UNIT_ID"] = unit_id
    td = _substitute(copy.deepcopy(document), bindings, used)
    if set(explicit) - used:
        raise AcquisitionError(f"unused TM parameters: {sorted(set(explicit) - used)}")
    _check_depth(td)
    validate_standard(td, kind=kind)
    if td.get("modpoll:version") != VERSION:
        raise AcquisitionError("expected contract 0.2")
    validate_extension(td, version="0.2")
    for key in (
        "actions",
        "events",
        "links",
        "forms",
        "uriVariables",
        "tm:optional",
        "tm:extends",
        "base",
    ):
        if td.get(key):
            raise AcquisitionError(f"/{key}: unsupported executable profile feature")
    if any(key.startswith("modv:") for key in td):
        raise AcquisitionError(
            "root Modbus fields are unsupported; use Forms or instance arguments"
        )
    if any(
        key.startswith("modpoll:")
        and key not in ("modpoll:version", "modpoll:acquisition")
        for key in td
    ):
        raise AcquisitionError("unsupported root project extension")
    contexts = {}
    for item in td.get("@context", []):
        if isinstance(item, dict):
            contexts.update(item)
    if (
        contexts.get("modpoll")
        != "https://top-maker.github.io/modpoll/vocab/wot-modbus#"
        or contexts.get("modv") != "https://www.w3.org/2019/wot/modbus"
        or contexts.get("xsd") != "http://www.w3.org/2001/XMLSchema#"
    ):
        raise AcquisitionError("unsupported fixed vocabulary aliases")
    # Validate explicit overrides even if a document has no bound Forms.
    if unit_id is not None and (type(unit_id) is not int or not 1 <= unit_id <= 254):
        raise AcquisitionError("unit_id: expected integer between 1 and 254")
    if port is not None and (type(port) is not int or not 1 <= port <= 65535):
        raise AcquisitionError("port: expected integer between 1 and 65535")
    if host is not None:
        _authority(host, 502 if port is None else port)
    metadata, declared_endpoint = {}, None
    declared_unit = None
    properties = td.get("properties", {})
    if not properties:
        raise AcquisitionError("/properties: expected nonempty object")
    for name, prop in properties.items():
        path = f"/properties/{name}/forms"
        if any(key.startswith(("modpoll:", "modv:")) for key in prop):
            raise AcquisitionError(f"{path}: protocol metadata belongs in Forms")
        forms = prop.get("forms", [])
        if not isinstance(forms, list) or not forms:
            raise AcquisitionError(f"{path}: a property needs Forms")
        ops_seen, mapping = set(), None
        bound_forms = []
        for form in forms:
            entity = form.get("modv:entity")
            if entity not in (
                "Coil",
                "DiscreteInput",
                "HoldingRegister",
                "InputRegister",
            ):
                raise AcquisitionError(f"{path}: invalid entity")
            bits = entity in ("Coil", "DiscreteInput")
            if "href" in form:
                remote, uid, address, count = _td_endpoint(form, path)
                for key, val in (
                    ("modv:address", address),
                    ("modv:quantity", count),
                    ("modv:unitID", uid),
                ):
                    if key in form and (type(form[key]) is not int or form[key] != val):
                        raise AcquisitionError(f"{path}: href disagrees with {key}")
                endpoint = (remote, uid)
                if declared_endpoint is not None and endpoint != declared_endpoint:
                    raise AcquisitionError(f"{path}: multiple endpoints/Unit IDs")
                declared_endpoint = endpoint
            else:
                if kind == "td":
                    raise AcquisitionError(f"{path}: missing concrete href")
                address, count = form.get("modv:address"), form.get("modv:quantity", 1)
            form_unit = uid if "href" in form else form.get("modv:unitID")
            if form_unit is not None:
                if type(form_unit) is not int or not 1 <= form_unit <= 254:
                    raise AcquisitionError(f"{path}: invalid modv:unitID")
                if declared_unit is not None and declared_unit != form_unit:
                    raise AcquisitionError(f"{path}: inconsistent Unit IDs")
                declared_unit = form_unit
            if (
                type(address) is not int
                or type(count) is not int
                or not 0 <= address <= 65535
                or not 1 <= count <= (2000 if bits else 125)
                or address + count > 65536
            ):
                raise AcquisitionError(f"{path}: invalid Modbus span")
            endian = tuple(
                form.get(key, True)
                for key in ("modv:mostSignificantByte", "modv:mostSignificantWord")
            )
            if any(type(flag) is not bool for flag in endian):
                raise AcquisitionError(f"{path}: invalid byte order")
            dtype, scalar = _codec(form, prop, count, bits, path)
            _validate_media(form, prop, dtype, scalar, bits, endian, path)
            allowed = ([] if prop.get("writeOnly") else ["readproperty"]) + (
                [] if prop.get("readOnly") else ["writeproperty"]
            )
            ops = form.get("op", allowed)
            if isinstance(ops, str):
                ops = [ops]
            if not ops or any(op not in allowed or op in ops_seen for op in ops):
                raise AcquisitionError(f"{path}: ambiguous or invalid operation")
            form.setdefault("contentType", "application/octet-stream")
            form["op"] = ops[0] if len(ops) == 1 else ops
            ops_seen.update(ops)
            current = (
                entity,
                address,
                count,
                dtype,
                endian,
                scalar,
                form.get("modpoll:bit"),
                form.get("modpoll:multiplier"),
            )
            if mapping is not None and mapping != current:
                raise AcquisitionError(f"{path}: read/write Forms disagree")
            mapping = current
            form["modv:address"], form["modv:quantity"] = address, count
            bound_forms.append(form)
        if ops_seen != set(allowed):
            raise AcquisitionError(f"{path}: Forms must cover property access")
        metadata[name] = (mapping, bound_forms)
    remote, uid = declared_endpoint or (
        None,
        1 if declared_unit is None else declared_unit,
    )
    if remote is not None:
        # Parse validated authority through an existing URL, preserving IPv6.
        from urllib.parse import urlsplit

        parsed = urlsplit("modbus+tcp://" + remote)
        actual_host, actual_port = parsed.hostname, parsed.port
    else:
        actual_host, actual_port = None, 502
    actual_host = actual_host if host is None else host
    actual_port = actual_port if port is None else port
    uid = uid if unit_id is None else unit_id
    authority = (
        _authority(actual_host, actual_port) if actual_host is not None else None
    )
    if authority is not None:
        from urllib.parse import urlsplit

        effective = urlsplit("modbus+tcp://" + authority)
        actual_host, actual_port = effective.hostname, effective.port
    if authority is None and kind == "td":
        raise AcquisitionError("TD requires a concrete endpoint")
    # Per-property legacy checks reuse established codec/access validation without
    # forcing unrelated members to share a byte order or eight-bit-group address.
    validated = {}
    for name, (mapping, forms) in metadata.items():
        entity, address, count, dtype, endian, scalar, bit, multiplier = mapping
        bits = entity in ("Coil", "DiscreteInput")
        legacy_prop = copy.deepcopy(properties[name])
        legacy_prop.pop("forms", None)
        if scalar:
            legacy_prop["type"] = "array" if bits else "integer"
            if bits:
                legacy_prop["items"] = {"type": "boolean"}
        member = {
            "modpoll:property": name,
            "modpoll:offset": 0,
            "modpoll:dataType": dtype,
        }
        if bit is not None:
            member["modpoll:bit"] = bit
        if multiplier is not None:
            member["modpoll:multiplier"] = multiplier
        check = {
            "@context": td["@context"],
            "@type": "tm:ThingModel",
            "title": td["title"],
            "modpoll:version": "0.1",
            "securityDefinitions": td.get("securityDefinitions", {}),
            "security": td.get("security", []),
            "properties": {name: legacy_prop},
            "modpoll:acquisition": [
                {
                    "modv:entity": entity,
                    "modv:address": address,
                    "modv:quantity": count,
                    "modv:mostSignificantByte": endian[0],
                    "modv:mostSignificantWord": endian[1],
                    "modpoll:members": [member],
                }
            ],
        }
        for key in ("security", "securityDefinitions"):
            if key not in td:
                check.pop(key, None)
        old = parse_model(check, unit_id=uid).groups[0].members[0]
        validated[name] = replace(
            old,
            byte_order=("BE" if endian[0] else "LE")
            + "_"
            + ("BE" if endian[1] else "LE"),
            physical_bits=bits,
            bit_count=count if bits else None,
            scalar=scalar,
        )
        for form in forms:
            if "modv:unitID" in form:
                form["modv:unitID"] = uid
            if authority is not None:
                form["href"] = (
                    f"modbus+tcp://{authority}/{uid}/{address}?quantity={count}"
                )
            else:
                form.pop("href", None)
    groups, seen = [], set()
    tables = {
        "Coil": "coil",
        "DiscreteInput": "discrete_input",
        "InputRegister": "input_register",
        "HoldingRegister": "holding_register",
    }
    for index, group in enumerate(td["modpoll:acquisition"]):
        entity, start, count = (
            group["modv:entity"],
            group["modv:address"],
            group["modv:quantity"],
        )
        if (
            type(start) is not int
            or type(count) is not int
            or count > (2000 if entity in ("Coil", "DiscreteInput") else 125)
            or start + count > 65536
        ):
            raise AcquisitionError(f"/modpoll:acquisition/{index}: invalid group span")
        members = []
        for name in group["modpoll:members"]:
            if name not in metadata or name in seen:
                raise AcquisitionError(
                    f"/modpoll:acquisition/{index}: unknown or duplicate member {name}"
                )
            mapping = metadata[name][0]
            if (
                mapping[0] != entity
                or mapping[1] < start
                or mapping[1] + mapping[2] > start + count
            ):
                raise AcquisitionError(
                    f"/modpoll:acquisition/{index}: member outside group or wrong entity"
                )
            members.append(replace(validated[name], offset=mapping[1] - start))
            seen.add(name)
        groups.append(Group(tables[entity], start, count, "BE_BE", tuple(members)))
    if seen != properties.keys():
        raise AcquisitionError(
            "every property must belong to exactly one acquisition group"
        )
    types = td.pop("@type", [])
    if isinstance(types, str):
        types = [types]
    types = [item for item in types if item != "tm:ThingModel"]
    if types:
        td["@type"] = types
    if "security" not in td:
        td.setdefault("securityDefinitions", {})["nosec_sc"] = {"scheme": "nosec"}
        td["security"] = "nosec_sc"
    # An unbound TM execution plan is valid, but is not an exportable TD.
    if authority is not None:
        validate_standard(td, kind="td")
        validate_modbus(td)
    from .loading import Model

    schemas = {
        name: {key: value for key, value in prop.items() if key != "forms"}
        for name, prop in properties.items()
    }
    model = Model(
        td["title"],
        kind,
        tuple(groups),
        uid,
        (actual_host, actual_port) if authority else None,
        json.dumps(schemas, sort_keys=True, ensure_ascii=False),
        VERSION,
    )
    return model, td


def export_td(document, *, target="project", **instance):
    model, td = instantiate(document, **instance)
    if any(
        "href" not in form
        for prop in td["properties"].values()
        for form in prop["forms"]
    ):
        raise AcquisitionError(
            "concrete TD export requires a TCP endpoint; serial/UDP execution remains available"
        )
    if target == "project":
        return td
    if target != "node-wot-0.9.2":
        raise AcquisitionError("unknown export target")
    failures = []
    for group in model.groups:
        for member in group.members:
            name = member.property
            prop = td["properties"][name]
            native_bit = (
                member.physical_bits and member.scalar and member.data_type == "bool"
            )
            if (
                member.multiplier is not None
                or member.bit is not None
                or (
                    not native_bit
                    and member.data_type
                    not in ("int16", "uint16", "int32", "uint32", "float32", "float64")
                )
                or (member.physical_bits and not native_bit)
            ):
                failures.append(name)
                continue
            converted = []
            for form in prop["forms"]:
                length = 1 if native_bit else type_width(member.data_type) * 2
                endian = {
                    "BE_BE": "BIG_ENDIAN",
                    "LE_LE": "LITTLE_ENDIAN",
                    "LE_BE": "BIG_ENDIAN_BYTE_SWAP",
                    "BE_LE": "LITTLE_ENDIAN_BYTE_SWAP",
                }[member.byte_order]
                if length == 2:
                    endian = (
                        "BIG_ENDIAN"
                        if member.byte_order.startswith("BE_")
                        else "LITTLE_ENDIAN"
                    )
                if (
                    member.writable
                    and length > 2
                    and member.byte_order in ("BE_LE", "LE_BE")
                ):
                    failures.append(name + " (node-wot mixed-order write codec)")
                    continue
                signed = (
                    "false"
                    if member.data_type.startswith("uint") or native_bit
                    else "true"
                )
                form["contentType"] = (
                    f"application/octet-stream;length={length};signed={signed};byteSeq={endian}"
                )
                ops = form.get(
                    "op",
                    (
                        ["readproperty"]
                        if prop.get("readOnly")
                        else (
                            ["writeproperty"]
                            if prop.get("writeOnly")
                            else ["readproperty", "writeproperty"]
                        )
                    ),
                )
                if isinstance(ops, str):
                    ops = [ops]
                # FC16 avoids node-wot's FC6 byte swapping of little-endian
                # two-byte writes. Separate operation Forms are standard TD.
                if not native_bit and "writeproperty" in ops:
                    if "readproperty" in ops:
                        read = copy.deepcopy(form)
                        read["op"] = "readproperty"
                        converted.append(read)
                    write = copy.deepcopy(form)
                    write["op"] = "writeproperty"
                    write.pop("modv:entity", None)
                    write["modv:function"] = "writeMultipleHoldingRegisters"
                    converted.append(write)
                else:
                    converted.append(form)
            prop["forms"] = converted
    if failures:
        raise AcquisitionError(
            "node-wot export cannot preserve semantics for: " + ", ".join(failures)
        )
    td.pop("modpoll:version", None)
    td.pop("modpoll:acquisition", None)
    validate_standard(td, kind="td")
    validate_modbus(td)
    return td
