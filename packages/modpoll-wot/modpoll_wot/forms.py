"""Check any declared Modbus Forms against the acquisition mapping."""

from urllib.parse import parse_qs, urlsplit

from .acquisition import AcquisitionError, ENTITIES


def validate_forms(document, groups, unit_id, kind):
    endpoint = None
    for group in groups:
        entity = next(key for key, value in ENTITIES.items() if value == group.table)
        for member in group.members:
            forms = document["properties"][member.property].get("forms", [])
            for form in forms:
                path = f"/properties/{member.property}/forms"
                if any(key.startswith("modpoll:") for key in form):
                    raise AcquisitionError(
                        f"{path}: unsupported project Form extension"
                    )
                if form.get("modv:entity") != entity:
                    raise AcquisitionError(f"{path}: expected modv:entity {entity}")
                if "modv:function" in form or "modv:zeroBasedAddressing" in form:
                    raise AcquisitionError(
                        f"{path}: function overrides and deprecated addressing are unsupported"
                    )
                for term, expected in (
                    ("modv:mostSignificantByte", group.byte_order[:2] == "BE"),
                    ("modv:mostSignificantWord", group.byte_order[-2:] == "BE"),
                ):
                    if term in form and (
                        type(form[term]) is not bool or form[term] != expected
                    ):
                        raise AcquisitionError(
                            f"{path}: byte order disagrees with group"
                        )
                allowed = (["readproperty"] if member.readable else []) + (
                    ["writeproperty"] if member.writable else []
                )
                ops = form.get("op", allowed)
                if isinstance(ops, str):
                    ops = [ops]
                if not ops or any(op not in allowed for op in ops):
                    raise AcquisitionError(
                        f"{path}: operation disagrees with property access"
                    )
                expected_type = {
                    "uint16": "xsd:unsignedShort",
                    "int16": "xsd:short",
                    "uint32": "xsd:unsignedInt",
                    "int32": "xsd:int",
                    "uint64": "xsd:unsignedLong",
                    "int64": "xsd:long",
                    "float32": "xsd:float",
                    "float64": "xsd:double",
                }.get(member.data_type)
                if member.data_type.startswith("string"):
                    expected_type = "xsd:string"
                elif member.data_type.startswith("bool"):
                    expected_type = (
                        "xsd:unsignedShort" if member.bit is not None else "xsd:boolean"
                    )
                if "modv:type" in form and (
                    expected_type is None or form["modv:type"] != expected_type
                ):
                    raise AcquisitionError(
                        f"{path}: modv:type disagrees with decoding type"
                    )
                supported = {
                    "modv:entity",
                    "modv:address",
                    "modv:unitID",
                    "modv:quantity",
                    "modv:mostSignificantByte",
                    "modv:mostSignificantWord",
                    "modv:type",
                }
                if any(
                    key.startswith("modv:") and key not in supported for key in form
                ):
                    raise AcquisitionError(f"{path}: unsupported Modbus form term")
                if (
                    form.get("contentType", "application/octet-stream")
                    != "application/octet-stream"
                ):
                    raise AcquisitionError(f"{path}: unsupported content type")
                href = form.get("href")
                if href is None and kind == "tm":
                    continue
                if not isinstance(href, str):
                    raise AcquisitionError(f"{path}: missing href")
                if "://" not in href:
                    base = document.get("base", "")
                    href = base.rstrip("/") + "/" + href
                try:
                    url = urlsplit(href)
                    parts = url.path.strip("/").split("/")
                    query = parse_qs(
                        url.query, strict_parsing=True, keep_blank_values=True
                    )
                    actual_unit, address = map(int, parts)
                    quantity = int(query.get("quantity", ["1"])[0])
                    if set(query) - {"quantity"} or len(query.get("quantity", [])) > 1:
                        raise ValueError("unsupported query")
                    remote = (url.hostname, url.port or 502)
                    if (
                        url.scheme != "modbus+tcp"
                        or not remote[0]
                        or url.username
                        or url.password
                        or url.fragment
                    ):
                        raise ValueError("invalid Modbus TCP URL")
                except (TypeError, ValueError) as exc:
                    raise AcquisitionError(f"{path}: invalid Modbus TCP href") from exc
                for term, value in (
                    ("modv:address", address),
                    ("modv:quantity", quantity),
                    ("modv:unitID", actual_unit),
                ):
                    if term in form and (
                        type(form[term]) is not int or form[term] != value
                    ):
                        raise AcquisitionError(
                            f"{path}: Modbus URL term disagrees with href"
                        )
                bit_table = group.table in ("coil", "discrete_input")
                expected_address = group.start + member.offset * (8 if bit_table else 1)
                expected_quantity = (
                    min(member.bit_group_width * 8, group.quantity - member.offset * 8)
                    if bit_table
                    else member.width
                )
                if (actual_unit, address, quantity) != (
                    unit_id,
                    expected_address,
                    expected_quantity,
                ):
                    raise AcquisitionError(
                        f"{path}: href disagrees with group/member or Unit ID"
                    )
                if endpoint is not None and endpoint != remote:
                    raise AcquisitionError(
                        f"{path}: multiple endpoints in one device are unsupported"
                    )
                endpoint = remote
