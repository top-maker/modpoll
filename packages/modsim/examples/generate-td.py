"""Generate loopback TD examples from canonical TM sources; never edit TDs by hand."""

import argparse
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
PRODUCTS = {
    "adam-5017uh": "adam-5017uh-slot-0-raw",
    "adam-6024": "adam-6024-raw",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="Fail if generated examples are stale"
    )
    args = parser.parse_args()
    try:
        from modpoll_wot import export_td
        from modpoll_wot.loading import load_document
    except ImportError:
        parser.error(
            "requires the modpoll-wot 0.2.0a1 candidate tool environment; see examples/README.md"
        )
    changed = []
    for product, stem in PRODUCTS.items():
        directory = ROOT / product
        source = directory / f"{stem}.tm.json"
        model = load_document(source)
        artifacts = {}
        outputs = {}
        for target, suffix in (
            ("project", "td.json"),
            ("node-wot-0.9.2", "node-wot.td.json"),
        ):
            document = export_td(
                model, host="127.0.0.1", port=5020, unit_id=1, target=target
            )
            payload = (
                json.dumps(document, indent=2, ensure_ascii=False) + "\n"
            ).encode()
            name = f"{stem}.{suffix}"
            outputs[directory / name] = payload
            artifacts[name] = {
                "target": target,
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        manifest = {
            "source": source.name,
            "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "generator": {"package": "modpoll-wot", "version": version("modpoll-wot")},
            "instance": {"host": "127.0.0.1", "port": 5020, "unit_id": 1},
            "artifacts": artifacts,
        }
        outputs[directory / "generated.json"] = (
            json.dumps(manifest, indent=2) + "\n"
        ).encode()
        for path, payload in outputs.items():
            if not path.exists() or path.read_bytes() != payload:
                changed.append(str(path.relative_to(ROOT)))
                if not args.check:
                    path.write_bytes(payload)
    if args.check and changed:
        print("Stale generated files: " + ", ".join(changed), file=sys.stderr)
        return 1
    print(
        "Generated examples are current."
        if args.check
        else "Generated: " + ", ".join(changed)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
