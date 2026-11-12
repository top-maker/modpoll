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
