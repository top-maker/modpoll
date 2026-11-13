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
    assert "One of --config/-f is required" in (result.stderr + result.stdout)
    assert "Traceback" not in result.stderr + result.stdout


def test_config_accepts_csv_tm_and_td_by_content_detection():
    cases = [
        (["--config", "examples/modsim.csv"], "No communication method specified"),
        (["-f", "examples/modsim.tm.json"], "No communication method specified"),
        # A bound TD supplies its own TCP endpoint, so --udp exercises the
        # unbound-TM guard instead of opening a connection.
        (
            ["--config", "examples/modsim.generated.td.json", "--udp", "127.0.0.1"],
            "unbound TM",
        ),
    ]
    for argv, message in cases:
        result = run(*argv, "--once")
        output = result.stderr + result.stdout
        assert result.returncode == 2, output
        assert message in output, output


def test_removed_flags_are_rejected():
    for flag in (
        "--tm",
        "--thing-model",
        "--thing-description",
        "--td",
        "--device",
        "--full-read",
        "--chassis",
        "--firmware",
        "--configuration",
    ):
        result = run(flag, "examples/modsim.tm.json", "--once")
        assert result.returncode == 2, flag
        assert "unrecognized arguments" in result.stderr + result.stdout


def test_report_flag_reaches_the_transport_check():
    result = run("--config", "examples/modsim.tm.json", "--report", "-", "--once")
    assert result.returncode == 2
    assert "No communication method specified" in result.stderr + result.stdout


def test_confirm_without_report_is_refused():
    result = run("--config", "examples/modsim.tm.json", "--confirm", "all", "--once")
    assert result.returncode == 2
    assert "need --report" in result.stderr + result.stdout


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
