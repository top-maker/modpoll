"""Build publishable artifacts from executable project Thing Models."""

from dataclasses import dataclass
from hashlib import sha256
import json

from .acquisition import AcquisitionError
from .loading import _loads_document
from .profile import instantiate

FORM_FIELDS = (
    "modv:entity",
    "modv:address",
    "modv:quantity",
    "modv:type",
    "modv:mostSignificantByte",
    "modv:mostSignificantWord",
    "modpoll:codec",
    "modpoll:bit",
    "modpoll:multiplier",
    "modpoll:byteLength",
    "modpoll:bitPacking",
)
READ_FUNCTIONS = {
    "Coil": 1,
    "DiscreteInput": 2,
    "HoldingRegister": 3,
    "InputRegister": 4,
}


@dataclass(frozen=True)
class AuditArtifact:
    payload: bytes
    source_sha256: str
    sha256: str
    format_version: str = "audit-tm-v1"


def _parse_tm(payload):
    try:
        model, effective = instantiate(_loads_document(payload))
    except (ValueError, TypeError, RecursionError) as exc:
        raise AcquisitionError(str(exc)) from exc
    if model.kind != "tm":
        raise AcquisitionError("publication requires a project Thing Model")
    return model, effective


def derive_audit_tm(payload: bytes, *, title: str) -> AuditArtifact:
    """Rebuild a read-only TM using the audit selection and an approved title."""
    model, effective = _parse_tm(payload)
    if model.audit is None:
        raise AcquisitionError("publication requires a modpoll:audit plan")
    audit = {
        section: list(names)
        for section, names in (
            ("identity", model.audit.identity),
            ("status", model.audit.status),
        )
        if names
    }
    properties = {}
    groups = []
    for names in audit.values():
        for name in names:
            prop = effective["properties"][name]
            read_form = next(
                form
                for form in prop["forms"]
                if form["op"] == "readproperty"
                or isinstance(form["op"], list)
                and "readproperty" in form["op"]
            )
            form = {key: read_form[key] for key in FORM_FIELDS if key in read_form}
            form["op"] = "readproperty"
            public_prop = {"type": prop["type"], "readOnly": True, "forms": [form]}
            if prop["type"] == "array":
                public_prop["items"] = {"type": prop["items"]["type"]}
            properties[name] = public_prop
            groups.append(
                {
                    "modv:entity": form["modv:entity"],
                    "modv:address": form["modv:address"],
                    "modv:quantity": form["modv:quantity"],
                    "modpoll:members": [name],
                }
            )
    document = {
        "@context": [
            "https://www.w3.org/2022/wot/td/v1.1",
            {
                "modpoll": "https://top-maker.github.io/modpoll/vocab/wot-modbus#",
                "modv": "https://www.w3.org/2019/wot/modbus",
                "xsd": "http://www.w3.org/2001/XMLSchema#",
            },
        ],
        "@type": "tm:ThingModel",
        "title": title,
        "modpoll:version": model.profile_version,
        "properties": properties,
        "modpoll:acquisition": groups,
        "modpoll:audit": audit,
    }
    derived = json.dumps(
        document,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    _parse_tm(derived)
    return AuditArtifact(
        derived, sha256(payload).hexdigest(), sha256(derived).hexdigest()
    )


def project_point_table(payload: bytes) -> list[dict]:
    """Project executable point spans and decoder metadata from exact TM bytes."""
    model, effective = _parse_tm(payload)
    rows = []
    for group in model.groups:
        for member in group.members:
            form = effective["properties"][member.property]["forms"][0]
            entity = form["modv:entity"]
            rows.append(
                {
                    "property": member.property,
                    "entity": entity,
                    "address": form["modv:address"],
                    "quantity": form["modv:quantity"],
                    "read_function_code": (
                        READ_FUNCTIONS[entity] if member.readable else None
                    ),
                    "writable": member.writable,
                    "data_type": member.data_type,
                    "byte_order": member.byte_order,
                    "bit": member.bit,
                    "bit_packing": form.get("modpoll:bitPacking"),
                    "multiplier": (
                        str(member.multiplier)
                        if member.multiplier is not None
                        else None
                    ),
                    "unit": member.unit,
                }
            )
    return rows
