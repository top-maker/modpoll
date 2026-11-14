"""modsim depends on modpoll-wot through its top-level interface only and never on modpoll (WOT-05)."""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCES = [*(ROOT / "modsim").rglob("*.py"), *(ROOT / "tools").rglob("*.py")]


def _imports(path):
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            yield node.module


def _violations(rule):
    return sorted(
        f"{path.relative_to(ROOT)}: {name}"
        for path in SOURCES
        for name in _imports(path)
        if rule(name)
    )


def test_modpoll_wot_is_used_through_its_top_level_only():
    assert not _violations(lambda name: name.startswith("modpoll_wot."))


def test_modsim_does_not_import_modpoll():
    assert not _violations(lambda name: name == "modpoll" or name.startswith("modpoll."))
