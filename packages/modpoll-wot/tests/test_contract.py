"""Independent acceptance vectors for the profile 0.2 configuration contract."""

import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from modpoll_wot import AcquisitionError, export_td
from modpoll_wot.loading import load_model, loads_model, parse_model

ROOT = Path(__file__).resolve().parent
RAW_TYPES = {
    "uint16": ("xsd:unsignedShort", 1),
    "int16": ("xsd:short", 1),
    "uint32": ("xsd:unsignedInt", 2),
    "int32": ("xsd:int", 2),
    "float32": ("xsd:float", 2),
    "uint64": ("xsd:unsignedLong", 4),
    "int64": ("xsd:long", 4),
    "float64": ("xsd:double", 4),
}


def scalar(dtype="uint16", type_="integer"):
    form = {
        "modv:entity": "HoldingRegister",
        "modv:address": 0,
        "modv:quantity": 1,
        "modv:type": "xsd:unsignedShort",
    }
    if dtype in RAW_TYPES:
        form["modv:type"], form["modv:quantity"] = RAW_TYPES[dtype]
    elif dtype.startswith("string"):
        length = int(dtype[6:])
        form.update(
            {
                "modv:type": "xsd:string",
                "modv:quantity": (length + 1) // 2,
                "modpoll:byteLength": length,
            }
        )
    else:
        form.update(
            {
                "modv:type": "xsd:hexBinary",
                "modpoll:codec": dtype,
                "modv:quantity": 2 if dtype == "bool16" else 1,
            }
        )
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
        "title": "test",
        "modpoll:version": "0.2",
        "properties": {"value": {"type": type_, "readOnly": True, "forms": [form]}},
        "modpoll:acquisition": [
            {
                "modv:entity": "HoldingRegister",
                "modv:address": 0,
                "modv:quantity": 125,
                "modpoll:members": ["value"],
            }
        ],
    }


class ContractTests(unittest.TestCase):
    def test_numeric_and_string_types(self):
        for dtype, width in [
            ("uint16", 1),
            ("int16", 1),
            ("float16", 1),
            ("uint32", 2),
            ("int32", 2),
            ("float32", 2),
            ("uint64", 4),
            ("int64", 4),
            ("float64", 4),
            ("string3", 2),
            ("string16", 8),
        ]:
            with self.subTest(dtype=dtype):
                prop_type = "string" if dtype.startswith("string") else "number"
                self.assertEqual(
                    parse_model(scalar(dtype, prop_type)).groups[0].members[0].width,
                    width,
                )

    def test_boolean_arrays_and_register_bits(self):
        for entity in ("Coil", "DiscreteInput", "HoldingRegister", "InputRegister"):
            for dtype in ("bool", "bool8", "bool16"):
                with self.subTest(entity=entity, dtype=dtype):
                    d = scalar(dtype, "array")
                    prop = d["properties"]["value"]
                    prop["items"] = {"type": "boolean"}
                    form = prop["forms"][0]
                    form["modv:entity"] = entity
                    d["modpoll:acquisition"][0]["modv:entity"] = entity
                    if entity in ("Coil", "DiscreteInput"):
                        form.pop("modpoll:codec")
                        form.update({"modv:type": "xsd:boolean", "modv:quantity": 16})
                    self.assertTrue(parse_model(d).groups[0].members[0].readable)
        for bit in (0, 15):
            d = scalar(type_="boolean")
            d["properties"]["value"]["forms"][0]["modpoll:bit"] = bit
            self.assertEqual(parse_model(d).groups[0].members[0].bit, bit)

    def test_all_endian_combinations(self):
        for byte in (True, False):
            for word in (True, False):
                d = scalar()
                d["properties"]["value"]["forms"][0].update(
                    {"modv:mostSignificantByte": byte, "modv:mostSignificantWord": word}
                )
                self.assertEqual(
                    parse_model(d).groups[0].members[0].byte_order,
                    ("BE" if byte else "LE") + "_" + ("BE" if word else "LE"),
                )

    def test_access_and_multiplier(self):
        for flags, expected in [
            ({}, (True, True)),
            ({"readOnly": True}, (True, False)),
            ({"writeOnly": True}, (False, True)),
        ]:
            d = scalar(type_="number")
            prop = d["properties"]["value"]
            prop.pop("readOnly")
            prop.update(flags)
            prop["forms"][0]["modpoll:multiplier"] = "0"
            member = parse_model(d).groups[0].members[0]
            self.assertEqual((member.readable, member.writable), expected)
            self.assertEqual(member.multiplier, 0)
        for factor in ("-2", "0.001", "1e3"):
            d = scalar(type_="number")
            d["properties"]["value"]["forms"][0]["modpoll:multiplier"] = factor
            self.assertIsNotNone(parse_model(d).groups[0].members[0].multiplier)

    def test_semantic_failures(self):
        mutations = [
            lambda d, g, f: g.update({"modv:address": 65535}),
            lambda d, g, f: g.update({"modv:quantity": 126}),
            lambda d, g, f: g.update({"modv:quantity": 0}),
            lambda d, g, f: g.update({"modv:quantity": True}),
            lambda d, g, f: f.update({"modv:mostSignificantByte": "BE"}),
            lambda d, g, f: f.update({"modv:address": -1}),
            lambda d, g, f: f.update({"modv:address": 125}),
            lambda d, g, f: g.update({"modpoll:members": ["unknown"]}),
            lambda d, g, f: f.update({"modv:type": "unit32"}),
            lambda d, g, f: f.update({"modv:type": "xsd:float"}),
            lambda d, g, f: f.update({"modpoll:bit": 1}),
            lambda d, g, f: f.update({"modpoll:multiplier": "NaN"}),
            lambda d, g, f: f.update({"modpoll:multiplier": "1e9999"}),
            lambda d, g, f: f.update({"modpoll:multiplier": True}),
            lambda d, g, f: f.update({"modpoll:scale": 1}),
            lambda d, g, f: g["modpoll:members"].append("value"),
            lambda d, g, f: d["properties"].update(
                {"missing": copy.deepcopy(d["properties"]["value"])}
            ),
            lambda d, g, f: d["properties"]["value"].update({"writeOnly": True}),
            lambda d, g, f: d.update({"modpoll:unknown": 1}),
        ]
        for index, mutation in enumerate(mutations):
            with self.subTest(case=index):
                d = scalar()
                g = d["modpoll:acquisition"][0]
                f = d["properties"]["value"]["forms"][0]
                mutation(d, g, f)
                with self.assertRaises(AcquisitionError):
                    parse_model(d)

    def test_boundary_addresses_and_limits(self):
        for entity, count in [
            ("HoldingRegister", 125),
            ("InputRegister", 125),
            ("Coil", 2000),
            ("DiscreteInput", 2000),
        ]:
            d = scalar()
            form = d["properties"]["value"]["forms"][0]
            form.update({"modv:entity": entity, "modv:address": 65536 - count})
            if count == 2000:
                d["properties"]["value"].update(
                    {"type": "array", "items": {"type": "boolean"}}
                )
                form.update({"modv:type": "xsd:boolean", "modv:quantity": count})
            g = d["modpoll:acquisition"][0]
            g.update(
                {
                    "modv:entity": entity,
                    "modv:quantity": count,
                    "modv:address": 65536 - count,
                }
            )
            parse_model(d)
            g["modv:quantity"] += 1
            with self.assertRaises(AcquisitionError):
                parse_model(d)

    def test_offline_loading_limits_and_namespaces(self):
        with patch(
            "socket.create_connection", side_effect=AssertionError("network used")
        ):
            load_model(ROOT / "fixtures/modsim.tm.json")
            load_model(ROOT / "fixtures/modsim.generated.td.json")
        for text in (
            '{"a":1,"a":2}',
            "NaN",
            "1e9999",
            "[" * 80 + "0" + "]" * 80,
            " " * 1048577,
        ):
            with self.subTest(text=text[:20]), self.assertRaises(AcquisitionError):
                loads_model(text)
        d = scalar()
        d["@context"][1]["modpoll"] = "https://example.com/unknown#"
        with self.assertRaises(AcquisitionError):
            parse_model(d)

    def test_td_forms_cannot_disagree_with_acquisition(self):
        source = export_td(scalar(), host="localhost", port=5020)
        for change in [
            lambda f: f.update({"modv:address": 999}),
            lambda f: f.update({"modv:entity": "InputRegister"}),
            lambda f: f.update({"modv:function": "readHoldingRegisters"}),
            lambda f: f.update({"op": "invokeaction"}),
            lambda f: f.update({"href": "http://localhost/1/0"}),
            lambda f: f.update({"modv:quantity": 999}),
            lambda f: f.update({"modv:type": "xsd:string"}),
            lambda f: f.update({"href": "modbus+tcp://localhost:5020/1/0?quantity="}),
        ]:
            d = copy.deepcopy(source)
            change(d["properties"]["value"]["forms"][0])
            with self.assertRaises(AcquisitionError):
                parse_model(d)
