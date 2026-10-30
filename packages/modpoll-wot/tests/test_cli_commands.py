import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from io import StringIO

from modpoll_wot import __main__ as cli

if not hasattr(cli, "_result"):
    raise unittest.SkipTest("requires the candidate shared CLI")

_result = cli._result


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
                self.run_cli("new", "--title", "Meter", "--output", path).returncode,
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
                self.run_cli("new", "--title", "Meter", "--output", path).returncode,
                0,
            )
            path.write_text('{"x": 1, "x": 2}', encoding="utf-8")
            self.assertNotEqual(self.run_cli("validate", path).returncode, 0)

    def test_default_output_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            environment = os.environ.copy()
            environment["PYTHONPATH"] = os.pathsep.join(
                [
                    str(Path(__file__).resolve().parents[1]),
                    environment.get("PYTHONPATH", ""),
                ]
            )
            result = subprocess.run(
                [sys.executable, "-m", "modpoll_wot", "new", "--title", "Meter"],
                cwd=directory,
                text=True,
                capture_output=True,
                env=environment,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            path = Path(directory) / "Meter.tm.json"
            original = path.read_bytes()
            self.assertEqual(json.loads(original)["title"], "Meter")
            self.assertEqual(
                self.run_cli("validate", path, "--kind", "tm").returncode, 0
            )
            again = subprocess.run(
                [sys.executable, "-m", "modpoll_wot", "new", "--title", "Meter"],
                cwd=directory,
                text=True,
                capture_output=True,
                env=environment,
            )
            self.assertNotEqual(again.returncode, 0)
            self.assertEqual(path.read_bytes(), original)
            self.assertNotEqual(
                self.run_cli("new", "--title", "../escape").returncode, 0
            )

    def test_subcommands_are_discoverable_and_old_interface_is_rejected(self):
        help_text = self.run_cli("--help")
        self.assertEqual(help_text.returncode, 0)
        for command in ("validate", "new", "export"):
            self.assertIn(command, help_text.stdout)
        self.assertNotEqual(self.run_cli("--config", "model.json").returncode, 0)
        self.assertNotEqual(self.run_cli("model.json").returncode, 0)
        self.assertNotEqual(self.run_cli("generate", "--title", "Meter").returncode, 0)

    def test_validation_reports_checks_and_failure_stage(self):
        source = Path(__file__).resolve().parents[3] / "examples" / "modsim.tm.json"
        basic = self.run_cli("validate", source)
        self.assertEqual(basic.returncode, 0)
        self.assertIn("TM structure (WoT 1.1): passed", basic.stdout)
        self.assertIn("use --profile", basic.stdout)
        self.assertNotIn("\x1b[", basic.stdout)
        profile = self.run_cli("validate", source, "--profile")
        self.assertEqual(profile.returncode, 0, profile.stderr)
        self.assertIn("Executable profile 0.2: passed", profile.stdout)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "starter.json"
            self.assertEqual(
                self.run_cli("new", "--title", "Meter", "-o", path).returncode, 0
            )
            failure = self.run_cli("validate", path, "--profile")
            self.assertEqual(failure.returncode, 1)
            self.assertIn("TM structure (WoT 1.1): passed", failure.stdout)
            self.assertIn("Executable profile: failed", failure.stderr)
            path.write_text('{"@type": 42}', encoding="utf-8")
            invalid = self.run_cli("validate", path, "--kind", "tm")
            self.assertEqual(invalid.returncode, 1)
            self.assertIn("TM structure (WoT 1.1): failed", invalid.stderr)

    def test_color_only_on_terminal_and_respects_no_color(self):
        stream = StringIO()
        with patch.object(stream, "isatty", return_value=True), patch.dict(
            os.environ, {"TERM": "xterm"}, clear=True
        ):
            _result(True, "passed", stream=stream)
            self.assertIn("\x1b[32m", stream.getvalue())
            stream.seek(0)
            stream.truncate()
            with patch.dict(os.environ, {"NO_COLOR": "1"}):
                _result(False, "failed", stream=stream)
            self.assertNotIn("\x1b[", stream.getvalue())
            self.assertIn("✗", stream.getvalue())

    def test_td_generation_and_validation(self):
        source = Path(__file__).resolve().parents[3] / "examples" / "modsim.tm.json"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "instance.td.json"
            result = self.run_cli(
                "export",
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
                    "export",
                    path,
                    "--output",
                    Path(directory) / "other.json",
                ).returncode,
                0,
            )
