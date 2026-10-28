"""Contract-boundary checks for the isolated standards-first experiment."""

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from modpoll_wot import AcquisitionError, parse_model
from modpoll_wot.pilot import compile_model
from modpoll_wot.validation import validate_standard

FIXTURE = Path(__file__).parent / "fixtures/numeric-pilot.tm.json"


def source():
    return json.loads(FIXTURE.read_text())


class PilotTests(unittest.TestCase):
    def test_source_uses_no_duplicate_codec_fields_and_round_trips(self):
        document = source()
        original = copy.deepcopy(document)
        model, td = compile_model(document, host="127.0.0.1", port=5020, unit_id=7)
        self.assertEqual(document, original)
        self.assertEqual(model.kind, "tm")
        self.assertEqual(model.unit_id, 7)
        self.assertEqual(
            [(m.offset, m.data_type) for m in model.groups[0].members],
            [(0, "uint16"), (2, "int16"), (4, "float32")],
        )
        self.assertEqual((model.groups[0].start, model.groups[0].quantity), (40000, 8))
        validate_standard(td, kind="td")
        reread, second = compile_model(td)
        self.assertEqual(reread.kind, "td")
        self.assertEqual((model.groups, model.unit_id), (reread.groups, reread.unit_id))
        self.assertEqual(td, second)
        self.assertNotIn("modpoll:dataType", json.dumps(td))
        self.assertNotIn("modpoll:offset", json.dumps(td))
        self.assertEqual(
            td["properties"]["measurement"]["forms"][0]["href"],
            "modbus+tcp://127.0.0.1:5020/7/40004?quantity=2",
        )

    def test_default_loader_does_not_accidentally_accept_pilot(self):
        with self.assertRaises(AcquisitionError):
            parse_model(source())

    def test_all_numeric_widths_and_byte_order_defaults(self):
        vectors = [
            ("xsd:unsignedShort", "uint16", 1),
            ("xsd:short", "int16", 1),
            ("xsd:unsignedInt", "uint32", 2),
            ("xsd:int", "int32", 2),
            ("xsd:unsignedLong", "uint64", 4),
            ("xsd:long", "int64", 4),
            ("xsd:float", "float32", 2),
            ("xsd:double", "float64", 4),
        ]
        for raw, expected, width in vectors:
            with self.subTest(raw=raw):
                d = source()
                d["properties"] = {"counter": d["properties"]["counter"]}
                p = d["properties"]["counter"]
                p["type"] = (
                    "number" if raw in ("xsd:float", "xsd:double") else "integer"
                )
                p["forms"][0].update({"modv:type": raw, "modv:quantity": width})
                d["modpoll:acquisition"][0]["modpoll:members"] = ["counter"]
                model, _ = compile_model(d, host="localhost")
                self.assertEqual(model.groups[0].members[0].data_type, expected)
                self.assertEqual(model.groups[0].byte_order, "BE_BE")

    def test_rejects_ambiguous_or_unrepresentable_mapping(self):
        for case in (
            "multiple-forms",
            "outside",
            "width",
            "entity",
            "transform",
            "mixed-order",
            "duplicate-member",
            "unmapped",
            "unknown-member",
            "duplicate-codec",
            "wrong-schema",
            "unknown-type",
            "overflow",
        ):
            with self.subTest(case=case):
                d = source()
                form = d["properties"]["counter"]["forms"][0]
                group = d["modpoll:acquisition"][0]
                if case == "multiple-forms":
                    d["properties"]["counter"]["forms"].append(copy.deepcopy(form))
                elif case == "outside":
                    form["modv:address"] = 39999
                elif case == "width":
                    form["modv:quantity"] = 2
                elif case == "entity":
                    form["modv:entity"] = "InputRegister"
                elif case == "transform":
                    form["modpoll:multiplier"] = 0.1
                elif case == "mixed-order":
                    form["modv:mostSignificantWord"] = False
                elif case == "duplicate-member":
                    group["modpoll:members"].append("counter")
                elif case == "unmapped":
                    group["modpoll:members"].remove("counter")
                elif case == "unknown-member":
                    group["modpoll:members"].append("missing")
                elif case == "duplicate-codec":
                    group["modpoll:dataType"] = "uint16"
                elif case == "wrong-schema":
                    d["properties"]["measurement"]["type"] = "integer"
                elif case == "unknown-type":
                    form["modv:type"] = "xsd:decimal"
                elif case == "overflow":
                    group["modv:address"] = 65535
                    group["modv:quantity"] = 2
                with self.assertRaises(AcquisitionError):
                    compile_model(d, host="localhost")

    def test_td_conflicts_and_overrides_fail(self):
        _, td = compile_model(source(), host="localhost")
        for key in ("modv:address", "modv:quantity"):
            d = copy.deepcopy(td)
            d["properties"]["counter"]["forms"][0][key] += 1
            with self.subTest(key=key), self.assertRaisesRegex(
                AcquisitionError, "disagrees"
            ):
                compile_model(d)
        with self.assertRaisesRegex(AcquisitionError, "overrides"):
            compile_model(td, host="other-host")
        d = copy.deepcopy(td)
        d["properties"]["counter"]["forms"][0][
            "href"
        ] = "modbus+tcp://other-host:502/1/40000"
        with self.assertRaisesRegex(AcquisitionError, "multiple endpoints"):
            compile_model(d)

    def test_endpoint_validation_and_ipv6(self):
        for host in (None, "0.0.0.0", "::", "host/path", "bad host", "user@host"):
            with self.subTest(host=host), self.assertRaises(AcquisitionError):
                compile_model(source(), host=host)
        for port in (True, 0, 65536):
            with self.subTest(port=port), self.assertRaises(AcquisitionError):
                compile_model(source(), host="localhost", port=port)
        _, td = compile_model(source(), host="::1")
        self.assertIn("[::1]:502", td["properties"]["counter"]["forms"][0]["href"])
        compile_model(td)

    def test_cli_uses_same_config_argument_without_extension(self):
        with tempfile.TemporaryDirectory() as temp:
            tm = Path(temp) / "source"
            td = Path(temp) / "instance.tm.json"
            again = Path(temp) / "roundtrip"
            tm.write_text(json.dumps(source()))
            command = [sys.executable, "-m", "modpoll_wot.pilot", "--config"]
            subprocess.run(
                command + [str(tm), "--host", "localhost", "--output", str(td)],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                command + [str(td), "--output", str(again)],
                check=True,
                capture_output=True,
            )
            self.assertEqual(json.loads(td.read_text()), json.loads(again.read_text()))


class PilotBoundaryTests(unittest.TestCase):
    def test_unresolved_templates_and_instance_defaults_are_rejected(self):
        for key, value in (("title", "Meter {{ID}}"), ("modv:unitID", 7)):
            d = source()
            d[key] = value
            with self.subTest(key=key), self.assertRaises(AcquisitionError):
                compile_model(d, host="localhost")

    def test_explicit_group_order_is_preserved(self):
        d = source()
        first = d["modpoll:acquisition"][0]
        first["modpoll:members"].remove("signed")
        d["modpoll:acquisition"].insert(
            0,
            {
                "modv:entity": "HoldingRegister",
                "modv:address": 40002,
                "modv:quantity": 1,
                "modpoll:members": ["signed"],
            },
        )
        model, td = compile_model(d, host="localhost")
        self.assertEqual(
            [(g.start, g.quantity) for g in model.groups], [(40002, 1), (40000, 8)]
        )
        self.assertEqual(model.groups, compile_model(td)[0].groups)

    def test_all_four_uniform_byte_orders(self):
        for byte in (True, False):
            for word in (True, False):
                d = source()
                for prop in d["properties"].values():
                    prop["forms"][0].update(
                        {
                            "modv:mostSignificantByte": byte,
                            "modv:mostSignificantWord": word,
                        }
                    )
                model, td = compile_model(d, host="localhost")
                with self.subTest(byte=byte, word=word):
                    self.assertEqual(model.groups, compile_model(td)[0].groups)
                    self.assertEqual(
                        model.groups[0].byte_order,
                        ("BE" if byte else "LE") + "_" + ("BE" if word else "LE"),
                    )
