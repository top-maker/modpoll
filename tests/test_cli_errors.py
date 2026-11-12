"""A mistake in the command line or model is one error line and exit code 2."""

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def run(*args):
    return subprocess.run(
        [sys.executable, "-m", "modpoll", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )


@pytest.mark.parametrize(
    "args, message",
    [
        (["--once"], "No communication method specified"),
        (["--tcp", "127.0.0.1", "--param", "BAD", "--once"], "invalid TM parameter"),
    ],
)
def test_configuration_errors_exit_2_without_a_traceback(args, message):
    result = run("--config", "examples/modsim.tm.json", *args)
    assert result.returncode == 2
    assert message in result.stderr + result.stdout
    assert "Traceback" not in result.stderr + result.stdout


def test_missing_configuration_exits_2():
    result = run("--once")
    assert result.returncode == 2
    assert (
        "One of -f/--tm, --thing-model, --thing-description or --device is required"
        in result.stderr + result.stdout
    )
    assert "Traceback" not in result.stderr + result.stdout


@pytest.mark.parametrize(
    "flag, config, extra",
    [
        ("--tm", "examples/modsim.tm.json", []),
        ("--thing-model", "examples/modsim.tm.json", []),
        # A bound TD supplies its own TCP endpoint, so --udp exercises the
        # unbound-TM guard instead of opening a connection.
        ("--td", "examples/modsim.generated.td.json", ["--udp", "127.0.0.1"]),
        (
            "--thing-description",
            "examples/modsim.generated.td.json",
            ["--udp", "127.0.0.1"],
        ),
    ],
)
def test_thing_model_and_description_flags_accept_json(flag, config, extra):
    result = run(flag, config, "--once", *extra)
    output = result.stderr + result.stdout
    assert result.returncode == 2
    assert (
        "No communication method specified" in output or "unbound TM" in output
    ), output


@pytest.mark.parametrize(
    "flag, config",
    [
        # --tm is the --config alias (local path, URL or modiohub reference);
        # v1 CSV is detected from the content there.
        ("--tm", "examples/modsim.csv"),
        ("-f", "examples/modsim.csv"),
    ],
)
def test_config_alias_accepts_csv_by_content_detection(flag, config):
    result = run(flag, config, "--once")
    assert result.returncode == 2
    assert "No communication method specified" in result.stderr + result.stdout


def test_thing_model_flag_rejects_csv_content():
    result = run("--thing-model", "examples/modsim.csv", "--tcp", "127.0.0.1", "--once")
    assert result.returncode == 2
    assert "expects a TM/TD JSON document" in result.stderr + result.stdout
    assert "Traceback" not in result.stderr + result.stdout


def test_csv_rejects_typed_parameters():
    result = run(
        "--config",
        "examples/modsim.csv",
        "--param",
        "GAIN=2",
        "--tcp",
        "127.0.0.1",
        "--once",
    )
    assert result.returncode == 2
    assert "--param requires a Thing Model" in result.stderr + result.stdout
    assert "Traceback" not in result.stderr + result.stdout
