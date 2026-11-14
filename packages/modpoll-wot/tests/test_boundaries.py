"""modpoll-wot stays an offline contract: no Modbus, MQTT or network client libraries (WOT-05)."""

import ast
from pathlib import Path
import subprocess
import sys

SOURCE = Path(__file__).resolve().parents[1] / "modpoll_wot"
FORBIDDEN = ("pymodbus", "paho", "requests", "urllib3", "httpx", "aiohttp", "serial")


def _imported_roots(path):
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            yield from (alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            yield node.module.split(".")[0]


def test_sources_import_no_device_or_network_library():
    found = {
        (path.name, root)
        for path in SOURCE.rglob("*.py")
        for root in _imported_roots(path)
        if root in FORBIDDEN
    }
    assert not found


def test_importing_the_package_loads_no_device_or_network_library():
    probe = (
        "import sys, modpoll_wot, modpoll_wot.__main__; "
        f"print(sorted(m for m in sys.modules if m.split('.')[0] in {FORBIDDEN!r}))"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, check=True
    )
    assert result.stdout.strip() == "[]"
