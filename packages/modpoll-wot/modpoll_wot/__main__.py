"""Offline TM/TD structure checks, executable profile checks and generation."""

import argparse
import json
import os
from pathlib import Path
import sys

from . import (
    AcquisitionError,
    export_td,
    load_model,
    point_fingerprints,
    validate_report,
    validate_standard,
)
from .simulation import load_simulation_data
from .loading import _document_kind, load_document
from .profile import parse_parameters
from .verification import combine_fingerprints


def _write_json(path, document):
    with Path(path).open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(document, indent=2, ensure_ascii=False) + "\n")


def _result(passed, message, *, stream):
    marker = "✓" if passed else "✗"
    try:
        marker.encode(stream.encoding or "utf-8")
    except (UnicodeEncodeError, LookupError):
        marker = "[PASS]" if passed else "[FAIL]"
    if (
        stream.isatty()
        and "NO_COLOR" not in os.environ
        and os.environ.get("TERM") != "dumb"
    ):
        marker = f"\033[{'32' if passed else '31'}m{marker}\033[0m"
    print(f"{marker} {message}", file=stream, flush=True)


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
    check.add_argument("--kind", choices=["auto", "tm", "td", "data"], default="auto")
    check.add_argument(
        "--profile", action="store_true", help="Also check executable profile"
    )
    _instance_options(check)
    new = commands.add_parser("new", help="Create a starter TM")
    new.add_argument("--title", required=True)
    new.add_argument("-o", "--output", help="Output path (default: <title>.tm.json)")
    export = commands.add_parser("export", help="Export a concrete TD from a TM")
    export.add_argument("input", help="Source TM file")
    export.add_argument("-o", "--output", required=True)
    export.add_argument(
        "--target", choices=["project", "node-wot-0.9.2"], default="project"
    )
    _instance_options(export)
    prints = commands.add_parser(
        "fingerprint", help="Print model and point fingerprints of a TM or TD as JSON"
    )
    prints.add_argument("input", help="Local JSON file")
    report = commands.add_parser(
        "validate-report", help="Validate a hardware verification report"
    )
    report.add_argument("input", help="Local report JSON file")
    report.add_argument(
        "--model", help="Exact TM bytes the report claims; checks hash and fingerprints"
    )
    args = parser.parse_args()
    phase = "Input"
    try:
        if args.command == "new":
            if not args.title.strip():
                raise AcquisitionError("title cannot be empty")
            if args.output is None and (
                args.title in (".", "..") or "/" in args.title or "\\" in args.title
            ):
                raise AcquisitionError(
                    "title cannot contain path separators; use --output"
                )
            output = args.output or f"{args.title}.tm.json"
            document = {
                "@context": "https://www.w3.org/2022/wot/td/v1.1",
                "title": args.title,
                "@type": "tm:ThingModel",
                "properties": {},
            }
            validate_standard(document, kind="tm")
            _write_json(output, document)
            print(f"Generated starter TM: {output} (no executable Modbus mappings)")
        elif args.command == "fingerprint":
            points = point_fingerprints(Path(args.input).read_bytes())
            result = {"model": combine_fingerprints(points.values()), "points": points}
            print(json.dumps(result, indent=2, ensure_ascii=False))
        elif args.command == "validate-report":
            phase = "Verification report"
            document = load_document(args.input)
            model = None if args.model is None else Path(args.model).read_bytes()
            validate_report(document, model=model)
            scope = "schema, hash and fingerprints" if model else "schema only"
            _result(True, f"{phase}: passed ({scope})", stream=sys.stdout)
        else:
            document = load_document(args.input)
            if not isinstance(document, dict):
                raise AcquisitionError(f"{args.input}: document: expected object")
            if args.command == "validate" and args.kind == "data":
                phase = "Simulation data"
                if args.profile:
                    raise AcquisitionError("--profile applies to TM and TD input")
                loaded = load_simulation_data(document)
                data = loaded.data
                counts = ", ".join(
                    f"{len(data.get(key, {}))} {key}"
                    for key in ("initial", "generators", "bindings")
                )
                _result(
                    True,
                    f"{phase} {data['version']}: passed ({loaded.source}; {counts})",
                    stream=sys.stdout,
                )
                if loaded.unread:
                    print(f"  Unread snapshot points left out: {', '.join(loaded.unread)}")
            elif args.command == "validate":
                if not args.profile and (
                    args.host is not None
                    or args.port is not None
                    or args.unit_id is not None
                    or args.param
                ):
                    phase = "Options"
                    raise AcquisitionError("instance options require --profile")
                kind = _document_kind(document) if args.kind == "auto" else args.kind
                phase = f"{kind.upper()} structure (WoT 1.1)"
                validate_standard(document, kind=kind)
                _result(True, f"{phase}: passed", stream=sys.stdout)
                if args.profile:
                    phase = "Executable profile"
                    model = load_model(
                        args.input,
                        kind=kind,
                        host=args.host,
                        port=args.port,
                        unit_id=args.unit_id,
                        parameters=parse_parameters(args.param),
                    )
                    _result(
                        True,
                        f"{phase} {model.profile_version}: passed ({model.title})",
                        stream=sys.stdout,
                    )
                    print("  Device behavior and point mappings were not tested.")
                else:
                    print(
                        "  JSON Schema only; use --profile to check project compatibility."
                    )
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
        if args.command in ("validate", "validate-report"):
            _result(False, f"{phase}: failed", stream=sys.stderr)
            print(f"  {exc}", file=sys.stderr)
        else:
            print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
