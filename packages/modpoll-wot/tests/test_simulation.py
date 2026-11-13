import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from modpoll_wot import DataError, load_simulation_data, scaled_raw


class SimulationDataTests(unittest.TestCase):
    def test_data_document_is_returned_unchanged(self):
        document = {
            "version": "1",
            "initial": {"VOLTAGE": 230.1, "RUNNING": True, "NAME": "SIM", "FLAGS": [True, False]},
            "generators": {"CURRENT": {"kind": "sine", "center": 5, "amplitude": 1, "period": 10}},
            "bindings": {"DO0": "DI0"},
            "tick": 0.5,
            "seed": 7,
            "writePolicy": "overwrite",
        }
        loaded = load_simulation_data(document)
        self.assertEqual((loaded.data, loaded.source, loaded.unread), (document, "data", ()))

    def test_executable_and_unknown_fields_are_rejected(self):
        for extra in ({"script": "behavior.py"}, {"parameters": {}}, {"vectors": {}}):
            with self.subTest(extra=extra), self.assertRaises(DataError):
                load_simulation_data({"version": "1", **extra})
        with self.assertRaises(DataError):
            load_simulation_data({"version": "2"})
        with self.assertRaises(DataError):
            load_simulation_data({"version": "1", "initial": {"A": {"nested": 1}}})
        with self.assertRaises(DataError):
            load_simulation_data({"version": "1", "tick": 0})

    def test_property_names_are_checked_when_given(self):
        document = {"version": "1", "initial": {"A": 1}, "bindings": {"B": "C"}}
        load_simulation_data(document, properties={"A", "B", "C"})
        with self.assertRaisesRegex(DataError, r"\['C'\]"):
            load_simulation_data(document, properties={"A", "B"})

    def test_snapshot_becomes_static_values(self):
        snapshot = {"ADAM-6024": {"AI0": 4660, "AI1": None, "timestamp": 1731400000.0}}
        loaded = load_simulation_data(snapshot, properties={"AI0", "AI1"})
        self.assertEqual(loaded.data, {"version": "1", "initial": {"AI0": 4660}})
        self.assertEqual((loaded.source, loaded.unread), ("snapshot", ("AI1",)))

    def test_snapshot_timestamp_is_a_point_only_when_the_model_has_one(self):
        snapshot = {"logger": {"timestamp": 42}}
        self.assertEqual(load_simulation_data(snapshot, properties={"timestamp"}).data["initial"], {"timestamp": 42})
        self.assertEqual(load_simulation_data(snapshot).data["initial"], {})

    def test_snapshot_device_is_selected_by_title(self):
        snapshot = {"meter": {"V": 230}, "module": {"AI0": 1}}
        self.assertEqual(load_simulation_data(snapshot, title="module").data["initial"], {"AI0": 1})
        with self.assertRaisesRegex(DataError, "none is titled"):
            load_simulation_data(snapshot, title="other")
        with self.assertRaises(DataError):
            load_simulation_data({"meter": 230})
        with self.assertRaises(DataError):
            load_simulation_data({})


class ScaledRawTests(unittest.TestCase):
    def test_exact_decimals_and_modpoll_floats_recover_the_raw_integer(self):
        self.assertEqual(scaled_raw(230.1, "0.1"), 2301)
        self.assertEqual(scaled_raw(230.10000000000002, "0.1"), 2301)
        self.assertEqual(scaled_raw(float(2301) * 0.1, "0.1"), 2301)
        self.assertEqual(scaled_raw(4.987, "0.001"), 4987)
        self.assertEqual(scaled_raw(-12, "1"), -12)
        self.assertEqual(scaled_raw(1200, "100"), 12)
        for raw in range(0, 70000, 7):
            for multiplier in ("0.1", "0.01", "0.001", "0.5"):
                value = float(raw) * float(multiplier)
                self.assertEqual(scaled_raw(value, multiplier), raw, (raw, multiplier))

    def test_other_values_are_rejected(self):
        for value, multiplier in ((230.15, "0.1"), (230.1000001, "0.1"), (1, "0"), (float("nan"), "1"), (True, "1"), ("1", "1")):
            with self.subTest(value=value, multiplier=multiplier), self.assertRaises(DataError):
                scaled_raw(value, multiplier)
        self.assertEqual(scaled_raw(0, "0"), 0)


class CommandTests(unittest.TestCase):
    def run_cli(self, document):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.json"
            path.write_text(json.dumps(document))
            return subprocess.run(
                [sys.executable, "-m", "modpoll_wot", "validate", str(path), "--kind", "data"],
                text=True, capture_output=True, env=os.environ.copy(),
            )

    def test_validate_data_and_snapshots(self):
        result = self.run_cli({"version": "1", "initial": {"A": 1}})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Simulation data 1: passed (data; 1 initial, 0 generators, 0 bindings)", result.stdout)
        result = self.run_cli({"device": {"A": 1, "B": None}})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("(snapshot; 1 initial", result.stdout)
        self.assertIn("Unread snapshot points left out: B", result.stdout)
        result = self.run_cli({"version": "1", "script": "x.py"})
        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
