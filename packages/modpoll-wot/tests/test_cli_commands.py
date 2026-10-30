import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class CommandTests(unittest.TestCase):
    def run_cli(self, *arguments):
        return subprocess.run(
            [sys.executable, "-m", "modpoll_wot", *map(str, arguments)],
            text=True,
            capture_output=True,
            env=os.environ.copy(),
        )

    def test_starter_and_structure_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "starter.tm.json"
            self.assertEqual(
                self.run_cli(
                    "generate", "tm", "--title", "Meter", "--output", path
                ).returncode,
                0,
            )
            self.assertEqual(
                self.run_cli("validate", path, "--kind", "tm").returncode, 0
            )
            self.assertNotEqual(
                self.run_cli("validate", path, "--kind", "tm", "--profile").returncode,
                0,
            )
            self.assertNotEqual(
                self.run_cli(
                    "generate", "tm", "--title", "Meter", "--output", path
                ).returncode,
                0,
            )
            path.write_text('{"x": 1, "x": 2}', encoding="utf-8")
            self.assertNotEqual(self.run_cli("validate", path).returncode, 0)

    def test_td_generation_and_validation(self):
        source = Path(__file__).resolve().parents[3] / "examples" / "modsim.tm.json"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "instance.td.json"
            result = self.run_cli(
                "generate",
                "td",
                "--input",
                source,
                "--host",
                "127.0.0.1",
                "--port",
                "5020",
                "--unit-id",
                "7",
                "--output",
                path,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                self.run_cli("validate", path, "--kind", "td", "--profile").returncode,
                0,
            )
            self.assertNotIn(
                "tm:ThingModel", json.loads(path.read_text()).get("@type", [])
            )
            self.assertNotEqual(
                self.run_cli(
                    "generate",
                    "td",
                    "--input",
                    path,
                    "--output",
                    Path(directory) / "other.json",
                ).returncode,
                0,
            )
