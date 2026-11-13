"""Publishing either line must preserve the other version and vocabulary."""

import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "assemble_docs",
    Path(__file__).resolve().parents[1] / ".github/scripts/assemble-docs.py",
)
docs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(docs)


def test_updates_preserve_other_line_vocabulary_and_git(tmp_path):
    stable, preview, site, vocab = [
        tmp_path / p for p in ("stable", "preview", "site", "vocab")
    ]
    for folder, text in ((stable, "CSV"), (preview, "TM/TD"), (vocab, "terms")):
        folder.mkdir()
        (folder / "index.html").write_text('<body class="docs">' + text + "</body>")
    (site / ".git").mkdir(parents=True)
    (site / ".git/config").write_text("unchanged")
    docs.assemble(stable, site, "1.x", root=True)
    docs.assemble(preview, site, "v2", vocab=vocab)
    assert "CSV" in (site / "index.html").read_text()
    assert "TM/TD" in (site / "v2/index.html").read_text()
    stable.joinpath("index.html").write_text("<body>CSV patch</body>")
    docs.assemble(stable, site, "1.x", root=True)
    assert "CSV patch" in (site / "index.html").read_text()
    assert "TM/TD" in (site / "v2/index.html").read_text()
    assert "terms" in (site / "vocab/index.html").read_text()
    assert (site / ".git/config").read_text() == "unchanged"
    assert (site / "index.html").read_text().count('id="modpoll-versions"') == 1
    assert (site / ".nojekyll").exists()


def test_invalid_or_overlapping_build_cannot_destroy_snapshot(tmp_path):
    site = tmp_path / "site"
    site.mkdir()
    index = site / "index.html"
    index.write_text("keep")
    for build, line in ((site, "1.x"), (tmp_path, "v2"), (site, "unknown")):
        with pytest.raises(ValueError):
            docs.assemble(build, site, line, root=True)
    assert index.read_text() == "keep"
