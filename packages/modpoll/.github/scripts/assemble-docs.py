"""Update one documentation line in a complete Pages snapshot, preserving others."""

import argparse
from pathlib import Path
import shutil

RESERVED = {".git", ".nojekyll", "1.x", "v2", "vocab"}
BANNER = '<nav id="modpoll-versions"><a href="/modpoll/1.x/">1.x (CSV)</a> | <a href="/modpoll/v2/">2.x preview (TM/TD)</a></nav>'


def copy_contents(source, target):
    target.mkdir(parents=True, exist_ok=True)
    for entry in source.iterdir():
        dest = target / entry.name
        if entry.is_dir():
            shutil.copytree(entry, dest, dirs_exist_ok=True)
        else:
            shutil.copy2(entry, dest)


def assemble(build, site, line, *, root=False, vocab=None):
    if line not in ("1.x", "v2") or not (build / "index.html").is_file():
        raise ValueError("invalid documentation line or missing build index")
    # Reject dangerous source/target overlap before deleting any generated files.
    if (
        build.resolve() == site.resolve()
        or site.resolve() in build.resolve().parents
        or build.resolve() in site.resolve().parents
    ):
        raise ValueError("build and snapshot must be separate trees")
    site.mkdir(parents=True, exist_ok=True)
    destination = site / line
    if destination.exists():
        shutil.rmtree(destination)
    copy_contents(build, destination)
    if root:
        for entry in site.iterdir():
            if entry.name not in RESERVED:
                if entry.is_dir():
                    shutil.rmtree(entry)
                else:
                    entry.unlink()
        copy_contents(build, site)
    if vocab:
        copy_contents(vocab, site / "vocab")
    for page in site.rglob("*.html"):
        if ".git" in page.parts:
            continue
        html = page.read_text()
        if 'id="modpoll-versions"' not in html:
            import re

            html = re.sub(
                r"(<body\b[^>]*>)",
                lambda m: m[1] + BANNER,
                html,
                count=1,
                flags=re.IGNORECASE,
            )
            page.write_text(html)
    (site / ".nojekyll").touch()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("build", type=Path)
    parser.add_argument("site", type=Path)
    parser.add_argument("line", choices=("1.x", "v2"))
    parser.add_argument("--root", action="store_true")
    parser.add_argument("--vocab", type=Path)
    args = parser.parse_args()
    assemble(args.build, args.site, args.line, root=args.root, vocab=args.vocab)


if __name__ == "__main__":
    main()
