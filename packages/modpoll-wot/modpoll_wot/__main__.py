"""Validate/instantiate TM or TD and optionally export a concrete TD, offline."""

import argparse
import json
from pathlib import Path
import sys

from . import AcquisitionError, load_model, instantiate, export_td, validate_standard
from .loading import load_document, _document_kind
from .profile import parse_parameters


def _write_json(path, document):
    with Path(path).open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(document, indent=2, ensure_ascii=False) + "\n")


def _commands(argv):
    parser = argparse.ArgumentParser(prog="modpoll-wot")
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser(
        "validate", help="Validate TM/TD structure or executable profile"
    )
    check.add_argument("input", help="Local JSON file")
    check.add_argument("--kind", choices=["auto", "tm", "td"], default="auto")
    check.add_argument(
        "--profile", action="store_true", help="Also validate the executable profile"
    )
    check.add_argument("--host")
    check.add_argument("--port", type=int)
    check.add_argument("--unit-id", type=int)
    check.add_argument("--param", action="append", default=[], metavar="NAME=JSON")
    generate = commands.add_parser(
        "generate", help="Generate a starter TM or a TD from an executable TM"
    )
    generate.add_argument("kind", choices=["tm", "td"])
    generate.add_argument("--output", required=True)
    generate.add_argument("--input", help="Source TM for TD generation")
    generate.add_argument("--title", help="Title for a starter TM")
    generate.add_argument("--host")
    generate.add_argument("--port", type=int)
    generate.add_argument("--unit-id", type=int)
    generate.add_argument("--param", action="append", default=[], metavar="NAME=JSON")
    generate.add_argument(
        "--target", choices=["project", "node-wot-0.9.2"], default="project"
    )
    args = parser.parse_args(argv)
    try:
        if args.command == "validate":
            document = load_document(args.input)
            if not isinstance(document, dict):
                raise AcquisitionError("document: expected object")
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
        elif args.kind == "tm":
            if (
                not args.title
                or args.input
                or args.host is not None
                or args.port is not None
                or args.unit_id is not None
                or args.param
                or args.target != "project"
            ):
                raise AcquisitionError(
                    "TM generation requires --title; input and instance options apply only to TD"
                )
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
            if not args.input or args.title:
                raise AcquisitionError(
                    "TD generation requires --input and does not accept --title"
                )
            document = load_document(args.input)
            if not isinstance(document, dict) or _document_kind(document) != "tm":
                raise AcquisitionError("TD generation requires a TM input")
            td = export_td(
                document,
                host=args.host,
                port=args.port,
                unit_id=args.unit_id,
                parameters=parse_parameters(args.param),
                target=args.target,
            )
            _write_json(args.output, td)
            print(f"Generated TD: {args.output}")
    except (ValueError, OSError, TypeError, RecursionError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


def main():
    if len(sys.argv) > 1 and sys.argv[1] in ("validate", "generate"):
        return _commands(sys.argv[1:])
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog="Use 'modpoll-wot validate --help' or 'modpoll-wot generate --help' for the new commands.",
    )
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
            _write_json(args.output, td)
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
