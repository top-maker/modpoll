"""Offline TM/TD structure checks, executable profile checks and generation."""

import argparse
import json
from pathlib import Path
import sys

from . import AcquisitionError, export_td, load_model, validate_standard
from .loading import _document_kind, load_document
from .profile import parse_parameters


def _write_json(path, document):
    with Path(path).open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(document, indent=2, ensure_ascii=False) + "\n")


def _instance_options(parser):
    parser.add_argument("--host")
    parser.add_argument("--port", type=int)
    parser.add_argument("--unit-id", type=int)
    parser.add_argument("--param", action="append", default=[], metavar="NAME=JSON")


def main():
    parser = argparse.ArgumentParser(prog="modpoll-wot", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("validate", help="Validate TM/TD structure")
    check.add_argument("input", help="Local JSON file")
    check.add_argument("--kind", choices=["auto", "tm", "td"], default="auto")
    check.add_argument(
        "--profile", action="store_true", help="Also check executable profile"
    )
    _instance_options(check)
    generate = commands.add_parser("generate", help="Generate a starter TM")
    generate.add_argument("--title", required=True)
    generate.add_argument("-o", "--output", required=True)
    export = commands.add_parser("export", help="Export a concrete TD from a TM")
    export.add_argument("input", help="Source TM file")
    export.add_argument("-o", "--output", required=True)
    export.add_argument(
        "--target", choices=["project", "node-wot-0.9.2"], default="project"
    )
    _instance_options(export)
    args = parser.parse_args()
    try:
        if args.command == "generate":
            document = {
                "@context": "https://www.w3.org/2022/wot/td/v1.1",
                "@type": "tm:ThingModel",
                "title": args.title,
                "properties": {},
            }
            validate_standard(document, kind="tm")
            _write_json(args.output, document)
            print(
                f"Generated starter TM: {args.output} (no executable Modbus mappings)"
            )
        else:
            document = load_document(args.input)
            if not isinstance(document, dict):
                raise AcquisitionError(f"{args.input}: document: expected object")
            if args.command == "validate":
                kind = _document_kind(document) if args.kind == "auto" else args.kind
                validate_standard(document, kind=kind)
                if args.profile:
                    model = load_model(
                        args.input,
                        kind=kind,
                        host=args.host,
                        port=args.port,
                        unit_id=args.unit_id,
                        parameters=parse_parameters(args.param),
                    )
                    print(
                        f"{kind.upper()} structure and executable profile passed: {model.title}"
                    )
                else:
                    if (
                        args.host is not None
                        or args.port is not None
                        or args.unit_id is not None
                        or args.param
                    ):
                        raise AcquisitionError("instance options require --profile")
                    print(f"{kind.upper()} 1.1 schema passed (structure only)")
            else:
                if _document_kind(document) != "tm":
                    raise AcquisitionError("TD export requires a TM input")
                td = export_td(
                    document,
                    host=args.host,
                    port=args.port,
                    unit_id=args.unit_id,
                    parameters=parse_parameters(args.param),
                    target=args.target,
                )
                _write_json(args.output, td)
                print(f"Exported TD: {args.output}")
    except (ValueError, OSError, TypeError, RecursionError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
