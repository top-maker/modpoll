"""Small explicitly constructed executable models for application tests."""

import json


def raw_form(dtype, address, *, quantity=None, entity="HoldingRegister", bit=None):
    raw_types = {
        "uint16": ("xsd:unsignedShort", 1),
        "int16": ("xsd:short", 1),
        "uint32": ("xsd:unsignedInt", 2),
        "int32": ("xsd:int", 2),
        "uint64": ("xsd:unsignedLong", 4),
        "int64": ("xsd:long", 4),
        "float32": ("xsd:float", 2),
        "float64": ("xsd:double", 4),
    }
    form = {"modv:entity": entity, "modv:address": address}
    if dtype in raw_types:
        raw_type, width = raw_types[dtype]
    elif dtype.startswith("string"):
        length = int(dtype[6:])
        raw_type, width = "xsd:string", (length + 1) // 2
        form["modpoll:byteLength"] = length
    elif bit is not None:
        raw_type, width = "xsd:unsignedShort", 1
        form["modpoll:bit"] = bit
    else:
        raw_type, width = "xsd:hexBinary", 2 if dtype == "bool16" else 1
        form["modpoll:codec"] = dtype
    form.update(
        {
            "modv:type": raw_type,
            "modv:quantity": width if quantity is None else quantity,
        }
    )
    return form


def meter_model(name="meter", start=0, count=1):
    return {
        "@context": [
            "https://www.w3.org/2022/wot/td/v1.1",
            {
                "modpoll": "https://top-maker.github.io/modpoll/vocab/wot-modbus#",
                "modv": "https://www.w3.org/2019/wot/modbus",
                "xsd": "http://www.w3.org/2001/XMLSchema#",
            },
        ],
        "@type": "tm:ThingModel",
        "title": name,
        "modpoll:version": "0.2",
        "properties": {
            "value": {
                "type": "integer",
                "readOnly": True,
                "forms": [raw_form("uint16", start)],
            }
        },
        "modpoll:acquisition": [
            {
                "modv:entity": "HoldingRegister",
                "modv:address": start,
                "modv:quantity": count,
                "modpoll:members": ["value"],
            }
        ],
    }


def write_meter(path, name="meter", start=0, count=1):
    path.write_text(json.dumps(meter_model(name, start, count)))
    return path
