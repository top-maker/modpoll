"""Published-contract candidate checks, including full legacy fixture coverage."""

import copy
import json
from pathlib import Path
import unittest

from modpoll_wot import AcquisitionError, load_model, parse_model

try:
    from modpoll_wot.profile import instantiate, export_td
except ImportError:
    raise unittest.SkipTest("requires the 0.2 candidate wheel/source")

ROOT = Path(__file__).resolve().parents[3]


def numeric():
    d = json.loads((Path(__file__).parent / "fixtures/numeric.tm.json").read_text())
    d["modpoll:version"] = "0.2"
    return d


class ProfileTests(unittest.TestCase):
    def test_shared_td_preserves_consistent_binary_media_parameters(self):
        source = numeric()
        form = source["properties"]["counter"]["forms"][0]
        form["contentType"] = (
            "application/octet-stream;length=2;signed=false;byteSeq=BIG_ENDIAN"
        )
        expected = instantiate(numeric(), host="localhost")[0].groups
        model, td = instantiate(source, host="localhost")
        self.assertEqual(model.groups, expected)
        self.assertEqual(instantiate(td)[0].groups, expected)
        self.assertEqual(
            td["properties"]["counter"]["forms"][0]["contentType"], form["contentType"]
        )
        self.assertIn("modpoll:acquisition", td)

    def test_binary_media_cannot_conflict_with_modbus_mapping(self):
        for parameters in (
            "length=4",
            "signed=true",
            "byteSeq=LITTLE_ENDIAN",
            "length=2;length=2",
            "unknown=value",
            "length",
            "",
        ):
            with self.subTest(parameters=parameters):
                source = numeric()
                source["properties"]["counter"]["forms"][0]["contentType"] = (
                    "application/octet-stream;" + parameters
                )
                with self.assertRaises((AcquisitionError, ValueError)):
                    instantiate(source, host="localhost")

    def test_full_modsim_fixture_preserves_groups_types_and_transforms(self):
        old = load_model(
            ROOT / "packages/modpoll-wot/tests/fixtures/modsim-0.1.tm.json"
        )
        new = load_model(ROOT / "examples/modsim.tm.json")
        self.assertEqual(
            [(g.table, g.start, g.quantity) for g in old.groups],
            [(g.table, g.start, g.quantity) for g in new.groups],
        )
        for before, after in zip(old.groups, new.groups):
            for a, b in zip(before.members, after.members):
                self.assertEqual(
                    (a.property, a.multiplier, a.readable, a.writable, a.unit),
                    (b.property, b.multiplier, b.readable, b.writable, b.unit),
                )
                self.assertEqual(a.offset * (8 if b.physical_bits else 1), b.offset)
                self.assertEqual(
                    a.data_type, b.data_type if not b.physical_bits else "bool8"
                )
        d = json.loads((ROOT / "examples/modsim.tm.json").read_text())
        model, td = instantiate(d, host="127.0.0.1", port=5020, unit_id=7)
        self.assertEqual(model.groups, instantiate(td)[0].groups)
        self.assertEqual(model.properties_json, instantiate(td)[0].properties_json)

    def test_mixed_orders_remain_in_one_block(self):
        d = numeric()
        d["properties"]["signed"]["forms"][0]["modv:mostSignificantByte"] = False
        m, td = instantiate(d, host="localhost")
        self.assertEqual(len(m.groups), 1)
        self.assertEqual(
            [p.byte_order for p in m.groups[0].members], ["BE_BE", "LE_BE", "BE_BE"]
        )
        self.assertEqual(m.groups, instantiate(td)[0].groups)

    def test_td_defaults_and_explicit_overrides_produce_effective_td(self):
        _, td = instantiate(numeric(), host="localhost", port=5020, unit_id=7)
        m, effective = instantiate(td, host="127.0.0.1", port=5021, unit_id=2)
        self.assertEqual(m.endpoint, ("127.0.0.1", 5021))
        self.assertEqual(m.unit_id, 2)
        self.assertEqual(m.groups, instantiate(effective)[0].groups)
        self.assertEqual(instantiate(td)[0].endpoint, ("localhost", 5020))
        d = copy.deepcopy(td)
        d["properties"]["counter"]["forms"][0]["modv:address"] = 1
        with self.assertRaisesRegex(AcquisitionError, "disagrees"):
            instantiate(d, host="other")

    def test_typed_placeholders_are_bound_and_validated(self):
        d = numeric()
        d["title"] = "meter {{NAME}}"
        d["properties"]["counter"]["maximum"] = "{{LIMIT}}"
        _, td = instantiate(
            d, host="localhost", parameters={"NAME": "one", "LIMIT": 100}
        )
        self.assertEqual(td["title"], "meter one")
        self.assertEqual(td["properties"]["counter"]["maximum"], 100)
        with self.assertRaisesRegex(AcquisitionError, "unbound"):
            instantiate(d, host="localhost")
        with self.assertRaisesRegex(AcquisitionError, "unused"):
            instantiate(numeric(), host="localhost", parameters={"TYPO": 1})
        with self.assertRaises(AcquisitionError):
            instantiate(d, host="localhost", parameters={"NAME": "one", "LIMIT": False})

    def test_unbound_tm_is_executable_but_cannot_export_tcp_td(self):
        self.assertIsNone(instantiate(numeric())[0].endpoint)
        with self.assertRaisesRegex(AcquisitionError, "TCP endpoint"):
            export_td(numeric())

    def test_read_and_write_forms_are_selected_by_operation(self):
        d = numeric()
        p = d["properties"]["counter"]
        p.pop("readOnly")
        read = p["forms"][0]
        write = copy.deepcopy(read)
        write["op"] = "writeproperty"
        p["forms"].append(write)
        instantiate(d)
        write["op"] = "readproperty"
        with self.assertRaisesRegex(AcquisitionError, "ambiguous"):
            instantiate(d)

    def test_custom_codecs_scaling_bits_and_odd_utf8_strings(self):
        for typ, raw, extra, schema, qty in [
            (
                "float16",
                "xsd:hexBinary",
                {"modpoll:codec": "float16"},
                {"type": "number"},
                1,
            ),
            ("string3", "xsd:string", {"modpoll:byteLength": 3}, {"type": "string"}, 2),
            ("bool", "xsd:unsignedShort", {"modpoll:bit": 15}, {"type": "boolean"}, 1),
            (
                "bool16",
                "xsd:hexBinary",
                {"modpoll:codec": "bool16"},
                {"type": "array", "items": {"type": "boolean"}},
                2,
            ),
        ]:
            d = numeric()
            form = {
                **d["properties"]["counter"]["forms"][0],
                "modv:type": raw,
                "modv:quantity": qty,
                **extra,
            }
            d["properties"] = {"counter": {**schema, "readOnly": True, "forms": [form]}}
            d["modpoll:acquisition"][0]["modpoll:members"] = ["counter"]
            with self.subTest(typ=typ):
                m, td = instantiate(d, host="localhost")
                self.assertEqual(m.groups[0].members[0].data_type, typ)
                self.assertEqual(m.groups, instantiate(td)[0].groups)
                with self.assertRaisesRegex(AcquisitionError, "cannot preserve"):
                    export_td(d, host="localhost", target="node-wot-0.9.2")
        for factor in (-0.1, 0, 1000):
            d = numeric()
            p = d["properties"]["counter"]
            p["type"] = "number"
            p["forms"][0]["modpoll:multiplier"] = factor
            self.assertEqual(
                str(instantiate(d)[0].groups[0].members[0].multiplier), str(factor)
            )
            with self.assertRaisesRegex(AcquisitionError, "cannot preserve"):
                export_td(d, host="localhost", target="node-wot-0.9.2")

    def test_rejects_invalid_groups_codecs_and_conflicts(self):
        for case in (
            "span",
            "duplicate",
            "unmapped",
            "width",
            "transform-bool",
            "codec",
            "unknown",
        ):
            d = numeric()
            f = d["properties"]["counter"]["forms"][0]
            if case == "span":
                f["modv:address"] = 39999
            elif case == "duplicate":
                d["modpoll:acquisition"][0]["modpoll:members"].append("counter")
            elif case == "unmapped":
                d["modpoll:acquisition"][0]["modpoll:members"].remove("counter")
            elif case == "width":
                f["modv:quantity"] = 2
            elif case == "transform-bool":
                f.update({"modv:type": "xsd:boolean", "modpoll:multiplier": 2})
            elif case == "codec":
                f["modpoll:codec"] = "uint16"
            elif case == "unknown":
                f["typo"] = 1
            with self.subTest(case=case), self.assertRaises(AcquisitionError):
                instantiate(d, host="localhost")


class ProfileCliTests(unittest.TestCase):
    def test_config_content_export_roundtrip_and_no_overwrite(self):
        import subprocess
        import sys
        import tempfile

        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "source.td.json"
            output = Path(temp) / "instance.tm.json"
            source.write_text(json.dumps(numeric()))
            command = [sys.executable, "-m", "modpoll_wot"]
            result = subprocess.run(
                command
                + [
                    "export",
                    str(source),
                    "--host",
                    "127.0.0.1",
                    "--unit-id",
                    "7",
                    "--output",
                    str(output),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Exported TD", result.stdout)
            reread = subprocess.run(
                command + ["validate", str(output), "--profile"],
                capture_output=True,
                text=True,
            )
            self.assertEqual(reread.returncode, 0, reread.stderr)
            self.assertIn("TD structure", reread.stdout)
            duplicate = subprocess.run(
                command
                + [
                    "export",
                    str(source),
                    "--host",
                    "localhost",
                    "--output",
                    str(output),
                ],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(duplicate.returncode, 0)
            self.assertEqual(
                json.loads(output.read_text())["properties"]["counter"]["forms"][0][
                    "href"
                ],
                "modbus+tcp://127.0.0.1:502/7/40000?quantity=1",
            )

    def test_duplicate_json_and_invalid_roots_fail_with_source(self):
        import subprocess
        import sys
        import tempfile

        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "broken"
            for text in ('{"title":"a","title":"b"}', "[]", "NaN"):
                source.write_text(text)
                result = subprocess.run(
                    [sys.executable, "-m", "modpoll_wot", "validate", str(source)],
                    capture_output=True,
                    text=True,
                )
                with self.subTest(text=text):
                    self.assertEqual(result.returncode, 1)
                    self.assertIn(str(source), result.stderr)
                    self.assertNotIn("Traceback", result.stderr)


class ExternalCapabilityTests(unittest.TestCase):
    def test_mixed_order_multiword_write_and_int64_fail_by_property(self):
        d = numeric()
        p = d["properties"]["measurement"]
        p["readOnly"] = False
        p["forms"][0]["op"] = ["readproperty", "writeproperty"]
        p["forms"][0]["modv:mostSignificantWord"] = False
        with self.assertRaisesRegex(AcquisitionError, "measurement.*mixed-order write"):
            export_td(d, host="localhost", target="node-wot-0.9.2")
        d = numeric()
        p = d["properties"]["measurement"]
        p["type"] = "integer"
        p["forms"][0].update({"modv:type": "xsd:unsignedLong", "modv:quantity": 4})
        with self.assertRaisesRegex(AcquisitionError, "measurement"):
            export_td(d, host="localhost", target="node-wot-0.9.2")


class PinnedBindingTests(unittest.TestCase):
    def test_official_binding_bytes_and_canonical_endpoints(self):
        import hashlib
        from importlib.resources import files

        payload = (
            files("modpoll_wot").joinpath("schemas", "modbus-binding.json").read_bytes()
        )
        self.assertEqual(
            hashlib.sha256(payload).hexdigest(),
            "284de7d3931e0093a87cc1180902ea395e338f0d9c09045af88ef6019f1b2611",
        )
        for host in ("LOCALHOST", "0:0:0:0:0:0:0:1"):
            with self.subTest(host=host):
                model, td = instantiate(numeric(), host=host)
                other, again = instantiate(td)
                self.assertEqual(model.endpoint, other.endpoint)
                self.assertEqual(td, again)
        for host in ("0.0.0.0", "::", "bad host", "user@host", "fe80::1%eth0"):
            with self.subTest(host=host), self.assertRaises(AcquisitionError):
                instantiate(numeric(), host=host)


class CanonicalFormTests(unittest.TestCase):
    def test_export_fills_binary_media_and_operations(self):
        d = numeric()
        form = d["properties"]["counter"]["forms"][0]
        form.pop("contentType")
        form.pop("op")
        td = export_td(d, host="localhost")
        effective = td["properties"]["counter"]["forms"][0]
        self.assertEqual(effective["contentType"], "application/octet-stream")
        self.assertEqual(effective["op"], "readproperty")
        self.assertNotIn("contentType", form)
        self.assertEqual(td, export_td(td))


class UnitIdFormTests(unittest.TestCase):
    def test_standard_unit_metadata_and_explicit_rebinding(self):
        d = numeric()
        for prop in d["properties"].values():
            prop["forms"][0]["modv:unitID"] = 7
        model, td = instantiate(d, host="localhost")
        self.assertEqual(model.unit_id, 7)
        rebound, effective = instantiate(td, unit_id=2)
        self.assertEqual(rebound.unit_id, 2)
        self.assertEqual(
            effective["properties"]["counter"]["forms"][0]["modv:unitID"], 2
        )
        self.assertEqual(instantiate(effective)[0].unit_id, 2)
        td["properties"]["counter"]["forms"][0]["modv:unitID"] = 8
        with self.assertRaisesRegex(AcquisitionError, "disagrees"):
            instantiate(td, unit_id=2)
