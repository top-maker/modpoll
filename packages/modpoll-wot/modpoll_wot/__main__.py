"""Validate/instantiate TM or TD and optionally export a concrete TD, offline."""

import argparse
import json
from pathlib import Path
import sys

from . import AcquisitionError, load_model, instantiate, export_td
from .loading import load_document
from .profile import parse_parameters


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model", nargs="?", help="Legacy positional configuration path")
    parser.add_argument("--config", help="TM or TD JSON; type detected from content")
    parser.add_argument("--host", help="Concrete TCP host for instantiation/export")
    parser.add_argument("--port", type=int)
    parser.add_argument("--unit-id", type=int)
    parser.add_argument("--param", action="append", default=[], metavar="NAME=JSON")
    parser.add_argument(
        "--output", help="Create a concrete TD file (must not already exist)"
    )
    parser.add_argument(
        "--target", choices=["project", "node-wot-0.9.2"], default="project"
    )
    args = parser.parse_args()
    if bool(args.model) == bool(args.config):
        parser.error(
            "provide one configuration using --config (or the legacy positional path)"
        )
    location = args.config or args.model
    try:
        parameters = parse_parameters(args.param)
        document = load_document(location)
        if not isinstance(document, dict):
            raise AcquisitionError("document: expected object")
        if document.get("modpoll:version") == "0.2":
            options = dict(
                host=args.host,
                port=args.port,
                unit_id=args.unit_id,
                parameters=parameters,
            )
            model, _ = instantiate(document, **options)
            td = (
                export_td(document, target=args.target, **options)
                if args.output
                else None
            )
        else:
            if (
                args.host is not None
                or args.port is not None
                or parameters
                or args.output
                or args.target != "project"
            ):
                raise AcquisitionError("instance binding/export requires contract 0.2")
            model = load_model(location, unit_id=args.unit_id)
            td = None
        if td is not None:
            with Path(args.output).open("x", encoding="utf-8") as stream:
                stream.write(json.dumps(td, indent=2, ensure_ascii=False) + "\n")
    except (ValueError, OSError, TypeError) as exc:
        print(f"{location}: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "title": model.title,
                "kind": model.kind,
                "unit_id": model.unit_id,
                "groups": len(model.groups),
                "properties": sum(len(g.members) for g in model.groups),
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
