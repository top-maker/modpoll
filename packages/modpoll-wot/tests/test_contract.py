"""Independent acceptance vectors for the configuration contract."""

import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from modpoll_wot import AcquisitionError
from modpoll_wot.loading import load_model, loads_model, parse_model

ROOT = Path(__file__).resolve().parents[3]


def scalar(dtype="uint16", type_="integer"):
    return {
        "@context": [
            "https://www.w3.org/2022/wot/td/v1.1",
            {
                "modpoll": "https://top-maker.github.io/modpoll/vocab/wot-modbus#",
                "modv": "https://www.w3.org/2019/wot/modbus",
            },
        ],
        "@type": "tm:ThingModel",
        "title": "test",
        "modpoll:version": "0.1",
        "properties": {"value": {"type": type_, "readOnly": True}},
        "modpoll:acquisition": [
            {
                "modv:entity": "HoldingRegister",
                "modv:address": 0,
                "modv:quantity": 125,
                "modv:mostSignificantByte": True,
                "modv:mostSignificantWord": True,
                "modpoll:members": [
                    {
                        "modpoll:property": "value",
                        "modpoll:offset": 0,
                        "modpoll:dataType": dtype,
                    }
                ],
            }
        ],
    }


class ContractTests(unittest.TestCase):
    def test_all_legacy_numeric_and_string_types(self):
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
                type_ = "string" if dtype.startswith("string") else "number"
                member = parse_model(scalar(dtype, type_)).groups[0].members[0]
                self.assertEqual(member.width, width)

    def test_bool_groups_and_register_bits(self):
        for entity in ("Coil", "DiscreteInput", "HoldingRegister", "InputRegister"):
            for dtype in ("bool", "bool8", "bool16"):
                with self.subTest(entity=entity, dtype=dtype):
                    d = scalar(dtype, "array")
                    d["properties"]["value"]["items"] = {"type": "boolean"}
                    d["modpoll:acquisition"][0]["modv:entity"] = entity
                    self.assertTrue(parse_model(d).groups[0].members[0].readable)
        for bit in (0, 15):
            d = scalar("bool", "boolean")
            d["modpoll:acquisition"][0]["modpoll:members"][0]["modpoll:bit"] = bit
            self.assertEqual(parse_model(d).groups[0].members[0].bit, bit)

    def test_all_endian_combinations(self):
        for byte in (True, False):
            for word in (True, False):
                d = scalar()
                g = d["modpoll:acquisition"][0]
                g["modv:mostSignificantByte"], g["modv:mostSignificantWord"] = (
                    byte,
                    word,
                )
                self.assertEqual(
                    parse_model(d).groups[0].byte_order,
                    ("BE" if byte else "LE") + "_" + ("BE" if word else "LE"),
                )

    def test_access_and_multiplier(self):
        for flags, expected in [
            ({}, (True, True)),
            ({"readOnly": True}, (True, False)),
            ({"writeOnly": True}, (False, True)),
        ]:
            d = scalar()
            d["properties"]["value"] = {"type": "number", **flags}
            d["modpoll:acquisition"][0]["modpoll:members"][0][
                "modpoll:multiplier"
            ] = "0"
            m = parse_model(d).groups[0].members[0]
            self.assertEqual((m.readable, m.writable), expected)
            self.assertEqual(m.multiplier, 0)
        for factor in ("-2", "0.001", "1e3"):
            d = scalar(type_="number")
            d["modpoll:acquisition"][0]["modpoll:members"][0][
                "modpoll:multiplier"
            ] = factor
            self.assertIsNotNone(parse_model(d).groups[0].members[0].multiplier)

    def test_semantic_failures(self):
        mutations = [
            lambda d, g, m: g.update({"modv:address": 65535}),
            lambda d, g, m: g.update({"modv:quantity": 126}),
            lambda d, g, m: g.update({"modv:quantity": 0}),
            lambda d, g, m: g.update({"modv:quantity": True}),
            lambda d, g, m: g.update({"modv:mostSignificantByte": "BE"}),
            lambda d, g, m: m.update({"modpoll:offset": -1}),
            lambda d, g, m: m.update({"modpoll:offset": 125}),
            lambda d, g, m: m.update({"modpoll:property": "unknown"}),
            lambda d, g, m: m.update({"modpoll:dataType": "unit32"}),
            lambda d, g, m: m.update({"modpoll:dataType": "float32"}),
            lambda d, g, m: m.update({"modpoll:bit": 1}),
            lambda d, g, m: m.update({"modpoll:multiplier": "NaN"}),
            lambda d, g, m: m.update({"modpoll:multiplier": "1e9999"}),
            lambda d, g, m: m.update({"modpoll:multiplier": True}),
            lambda d, g, m: m.update({"modpoll:scale": 1}),
            lambda d, g, m: g["modpoll:members"].append(copy.deepcopy(m)),
            lambda d, g, m: d["properties"].update({"missing": {"type": "number"}}),
            lambda d, g, m: d["properties"]["value"].update({"writeOnly": True}),
            lambda d, g, m: g.update({"modv:entity": "Coil", "modv:quantity": 8}),
            lambda d, g, m: d.update({"modpoll:unknown": 1}),
        ]
        for index, mutation in enumerate(mutations):
            with self.subTest(case=index):
                d = scalar()
                g = d["modpoll:acquisition"][0]
                m = g["modpoll:members"][0]
                mutation(d, g, m)
                with self.assertRaises(AcquisitionError):
                    parse_model(d)

    def test_boundary_addresses_and_limits(self):
        for entity, count in [
            ("HoldingRegister", 125),
            ("InputRegister", 125),
            ("Coil", 2000),
            ("DiscreteInput", 2000),
        ]:
            d = scalar("bool8", "array") if count == 2000 else scalar()
            if count == 2000:
                d["properties"]["value"]["items"] = {"type": "boolean"}
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
            load_model(ROOT / "examples/modsim.tm.json")
            load_model(ROOT / "examples/modsim.td.json")
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
        source = json.loads((ROOT / "examples/modsim.td.json").read_text())
        changes = [
            lambda f: f.update(
                {"href": "modbus+tcp://localhost:5020/1/999?quantity=8"}
            ),
            lambda f: f.update({"modv:entity": "InputRegister"}),
            lambda f: f.update({"modv:mostSignificantByte": False}),
            lambda f: f.update({"modv:function": "readHoldingRegisters"}),
            lambda f: f.update({"op": "invokeaction"}),
            lambda f: f.update({"href": "http://localhost/1/0"}),
        ]
        changes.extend(
            [
                lambda f: f.update({"modv:quantity": 999}),
                lambda f: f.update({"modv:type": "xsd:string"}),
                lambda f: f.update(
                    {"href": "modbus+tcp://localhost:5020/1/0?quantity="}
                ),
            ]
        )
        for change in changes:
            d = copy.deepcopy(source)
            change(d["properties"]["coil01-08"]["forms"][0])
            with self.assertRaises(AcquisitionError):
                parse_model(d)
