import json
from pathlib import Path
import tempfile
import unittest

from modpoll_wot import AcquisitionError
from modpoll_wot.loading import load_model, parse_model

FIXTURE = Path(__file__).resolve().parents[3] / "examples/modsim.tm.json"


class LoadingTests(unittest.TestCase):
    def test_modsim_four_tables_and_values_contract(self):
        model = load_model(FIXTURE, kind="tm")
        self.assertEqual(
            [(g.table, g.start, g.quantity) for g in model.groups],
            [
                ("coil", 0, 16),
                ("discrete_input", 10000, 16),
                ("input_register", 30000, 20),
                ("holding_register", 40000, 44),
            ],
        )
        self.assertEqual(sum(len(g.members) for g in model.groups), 37)
        self.assertFalse(model.groups[1].members[0].writable)
        self.assertTrue(model.groups[3].members[0].writable)
        self.assertEqual(str(model.groups[2].members[9].multiplier), "0.001")
        self.assertEqual(model.groups[3].members[-1].data_type, "string16")

    def test_unit_id_is_instance_input(self):
        self.assertEqual(load_model(FIXTURE, kind="tm", unit_id=7).unit_id, 7)
        for value in (True, 0, 255, "1"):
            with self.subTest(value=value), self.assertRaises(AcquisitionError):
                load_model(FIXTURE, kind="tm", unit_id=value)

    def test_authored_fixture_matches_csv_groups_and_members(self):
        import csv
        from decimal import Decimal

        source = Path(__file__).resolve().parents[3] / "examples/modsim.csv"
        model = load_model(FIXTURE, kind="tm")
        groups = []
        for row in csv.reader(source.read_text().splitlines()):
            if row[0] == "poll":
                groups.append((row, []))
            elif row[0] == "ref":
                groups[-1][1].append(row)
        self.assertEqual(len(groups), len(model.groups))
        for (poll, refs), group in zip(groups, model.groups):
            self.assertEqual(
                (poll[1], int(poll[2]), int(poll[3]), poll[4]),
                (group.table, group.start, group.quantity, group.byte_order),
            )
            self.assertEqual(len(refs), len(group.members))
            for row, member in zip(refs, group.members):
                self.assertEqual(
                    (row[1], int(row[2]) - group.start, row[3]),
                    (member.property, member.offset, member.data_type),
                )
                self.assertEqual(
                    Decimal(row[6]) if len(row) > 6 and row[6] else None,
                    member.multiplier,
                )

    def test_bad_json_and_semantics_include_filename(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "broken.json"
            for text in ('{"title":"a","title":"b"}', "{", "NaN"):
                path.write_text(text)
                with self.subTest(text=text), self.assertRaisesRegex(
                    AcquisitionError, "broken.json"
                ):
                    load_model(path, kind="tm")
            document = json.loads(FIXTURE.read_text())
            document["modpoll:acquisition"][1]["modpoll:members"][0]["modpoll:bit"] = 1
            path.write_text(json.dumps(document))
            with self.assertRaisesRegex(AcquisitionError, "bit selector"):
                load_model(path, kind="tm")

    def test_extension_schema_rejects_unknown_member(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "broken.json"
            document = json.loads(FIXTURE.read_text())
            document["modpoll:acquisition"][0]["modpoll:members"][0]["typo"] = 1
            path.write_text(json.dumps(document))
            with self.assertRaises(AcquisitionError):
                load_model(path, kind="tm")


class ModelUnitDefaultsTests(unittest.TestCase):
    def test_model_default_and_explicit_override(self):
        from modpoll_wot import parse_model

        document = json.loads(FIXTURE.read_text())
        document["modv:unitID"] = 7
        self.assertEqual(parse_model(document).unit_id, 7)
        self.assertEqual(parse_model(document, unit_id=2).unit_id, 2)
        for value in (0, 255, True, "7"):
            document["modv:unitID"] = value
            with self.subTest(value=value), self.assertRaises(AcquisitionError):
                parse_model(document)


class ContentDetectionTests(unittest.TestCase):
    def test_tm_marker_accepts_string_and_array_with_additional_type(self):
        for types in ("tm:ThingModel", ["urn:example:meter", "tm:ThingModel"]):
            document = json.loads(FIXTURE.read_text())
            document["@type"] = types
            with self.subTest(types=types):
                self.assertEqual(parse_model(document).kind, "tm")

    def test_explicit_python_kind_is_an_assertion_not_an_override(self):
        with self.assertRaisesRegex(AcquisitionError, "kind disagrees"):
            parse_model(json.loads(FIXTURE.read_text()), kind="td")

    def test_td_with_or_without_application_type(self):
        path = FIXTURE.with_name("modsim.td.json")
        for types in (None, "urn:example:meter", ["urn:example:meter"]):
            document = json.loads(path.read_text())
            if types is not None:
                document["@type"] = types
            with self.subTest(types=types):
                self.assertEqual(parse_model(document).kind, "td")

    def test_tm_filename_does_not_rescue_missing_marker(self):
        document = json.loads(FIXTURE.read_text())
        del document["@type"]
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "device.tm.json"
            path.write_text(json.dumps(document))
            with self.assertRaisesRegex(AcquisitionError, "device.tm.json"):
                load_model(path)

    def test_invalid_declared_tm_is_rejected(self):
        document = json.loads(FIXTURE.read_text())
        document["title"] = 12
        with self.assertRaises(AcquisitionError):
            parse_model(document)
