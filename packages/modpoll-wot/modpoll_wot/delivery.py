"""Project executable point tables from Thing Models."""

from .acquisition import AcquisitionError
from .loading import _loads_document
from .profile import instantiate
from .verification import canonical_point, fingerprint

READ_FUNCTIONS = {
    "Coil": 1,
    "DiscreteInput": 2,
    "HoldingRegister": 3,
    "InputRegister": 4,
}


def _parse_tm(payload):
    try:
        model, effective = instantiate(_loads_document(payload))
    except (ValueError, TypeError, RecursionError) as exc:
        raise AcquisitionError(str(exc)) from exc
    if model.kind != "tm":
        raise AcquisitionError("point tables require a project Thing Model")
    return model, effective


def project_point_table(payload: bytes) -> list[dict]:
    """Project executable point spans and decoder metadata from exact TM bytes."""
    model, effective = _parse_tm(payload)
    rows = []
    for group in model.groups:
        for member in group.members:
            prop = effective["properties"][member.property]
            form = prop["forms"][0]
            point = canonical_point(prop)
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
                    "fingerprint": fingerprint(point) if point else None,
                }
            )
    return rows
