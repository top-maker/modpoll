"""Two-level managed CLI; legacy flag-based server startup remains supported."""

import argparse
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from .management import RuntimeManager, paths, request, serve
from .manifest import load_deployment, read_yaml
from .utils import get_logger

ACTIONS = {"up", "down", "ps", "logs", "export", "reset"}


def default_deployment() -> str:
    """Select the example manifest from the repository root or examples directory."""
    if (Path.cwd() / "deployment.yaml").is_file():
        return "deployment.yaml"
    return "examples/deployment.yaml"


def default_output_dir() -> Path:
    """Use an ignored output directory at the project root."""
    return Path(__file__).resolve().parent.parent / "output"


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Manage a local Modsim deployment")
    actions = root.add_subparsers(dest="action", required=True)
    for action in sorted(ACTIONS):
        command = actions.add_parser(action)
        if action == "logs":
            command.add_argument("--file", default=default_deployment())
        else:
            command.add_argument("-f", "--file", default=default_deployment())
        if action == "up":
            command.add_argument("-d", "--detach", action="store_true")
            command.add_argument("--dry-run", action="store_true")
            command.add_argument("--allow-scripts", action="store_true")
            command.add_argument("--serve", action="store_true", help=argparse.SUPPRESS)
        if action == "logs":
            command.add_argument("-f", "--follow", action="store_true")
        if action in ("export", "reset"):
            command.add_argument("--device", required=action == "reset")
        if action == "export":
            output = command.add_mutually_exclusive_group()
            output.add_argument("-o", "--output")
            output.add_argument("--output-dir", default=str(default_output_dir()))
            command.add_argument("--running", action="store_true")
    return root


def identity(path: Path) -> str:
    if path.suffix.lower() not in (".yaml", ".yml"):
        raise ValueError("deployment file must use .yaml or .yml")
    spec = read_yaml(path)
    name = spec.get("name", path.parent.name)
    if not isinstance(name, str) or not name:
        raise ValueError("deployment name must be a nonempty string")
    return name


def call(name: str, path: Path, action: str, **options: object) -> dict:
    return asyncio.run(
        request(name, {"action": action, "source": str(path), **options})
    )


def online(name: str, path: Path) -> dict | None:
    try:
        return call(name, path, "ps")
    except (FileNotFoundError, ConnectionError):
        return None


def export_documents(tds: dict, args: argparse.Namespace) -> None:
    if args.device:
        if args.device not in tds:
            raise ValueError(f"unknown device: {args.device}")
        tds = {args.device: tds[args.device]}
    output = Path(args.output) if args.output else None
    output_is_directory = output is not None and (
        output.is_dir() or not output.suffix.lower() == ".json"
    )
    if output_is_directory and output is not None:
        output.mkdir(parents=True, exist_ok=True)
    if args.output_dir and output is None:
        Path(args.output_dir).mkdir(parents=True, exist_ok=True)
    for key, td in tds.items():
        target = (
            output / f"{key}.td.json"
            if output_is_directory and output is not None
            else (
                output
                if output is not None
                else Path(args.output_dir) / f"{key}.td.json"
            )
        )
        target.write_text(
            json.dumps(td, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(target)


def show_logs(name: str, path: Path, *, follow: bool = False) -> None:
    """Print recent output and optionally follow until the deployment stops."""
    log_path = paths(name)[2]
    if not log_path.exists():
        raise ValueError("no log for this deployment")
    with log_path.open("rb") as stream:
        stream.seek(max(0, log_path.stat().st_size - 1024 * 1024))
        while True:
            data = stream.read()
            if data:
                print(data.decode("utf-8", errors="replace"), end="", flush=True)
            if not follow or online(name, path) is None:
                break
            time.sleep(0.2)


def run(argv: list[str]) -> None:
    args = parser().parse_args(argv)
    get_logger()
    path = Path(args.file).resolve()
    try:
        name = identity(path)
        if args.action == "export":
            if args.running:
                try:
                    tds = call(name, path, "export")["tds"]
                except FileNotFoundError as exc:
                    raise ValueError(
                        "no managed deployment found in this environment; "
                        "start it with `poetry run modsim up -d`, or run export "
                        "inside the Docker Compose container"
                    ) from exc
            else:
                deployment = load_deployment(path, include_scenarios=False)
                tds = {key: item.td for key, item in deployment.instances.items()}
            export_documents(tds, args)
            return
        if args.action == "logs":
            # Verify the source if the deployment is currently running.
            online(name, path)
            show_logs(name, path, follow=args.follow)
            return
        if args.action != "up":
            status = online(name, path)
            if status is None:
                if args.action == "reset":
                    raise ValueError("deployment is not running")
                print(json.dumps({"running": False, "name": name}))
                return
            result = (
                status
                if args.action == "ps"
                else call(name, path, args.action, device=getattr(args, "device", None))
            )
            if args.action == "down":
                deadline = time.monotonic() + 10
                while online(name, path) is not None:
                    if time.monotonic() >= deadline:
                        raise ValueError(
                            "deployment shutdown did not complete within 10 seconds"
                        )
                    time.sleep(0.05)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return
        if args.serve:
            asyncio.run(serve(path, args.allow_scripts, detached=True))
        elif online(name, path):
            print(
                json.dumps(
                    call(
                        name,
                        path,
                        "up",
                        dry_run=args.dry_run,
                        allow_scripts=args.allow_scripts,
                    ),
                    indent=2,
                )
            )
            if not args.detach and not args.dry_run:
                try:
                    show_logs(name, path, follow=True)
                except KeyboardInterrupt:
                    # Detach from an existing deployment; its owner controls shutdown.
                    pass
        elif args.dry_run:

            async def preview() -> dict:
                manager = RuntimeManager(args.allow_scripts)
                return await manager.apply(load_deployment(path), dry_run=True)

            print(json.dumps(asyncio.run(preview()), indent=2))
        elif not args.detach:
            asyncio.run(serve(path, args.allow_scripts))
        else:
            # Resolve/validate before launching; the worker validates again from its snapshot.
            deployment = load_deployment(path)
            log_path = paths(deployment.name)[2]
            command = [sys.executable, "-m", "modsim", "up", "-f", str(path), "--serve"]
            if args.allow_scripts:
                command.append("--allow-scripts")
            with log_path.open("ab") as output:
                os.chmod(log_path, 0o600)
                process = subprocess.Popen(
                    command,
                    stdin=subprocess.DEVNULL,
                    stdout=output,
                    stderr=output,
                    start_new_session=True,
                )
            deadline = time.monotonic() + 30
            while process.poll() is None:
                status = online(name, path)
                if status:
                    print(json.dumps(status, ensure_ascii=False, indent=2))
                    return
                if time.monotonic() >= deadline:
                    process.terminate()
                    process.wait(timeout=10)
                    raise ValueError(f"startup timed out; inspect {log_path}")
                time.sleep(0.05)
            process.wait()
            raise ValueError(f"startup failed; inspect {log_path}")
    except KeyboardInterrupt:
        return
    except (ValueError, OSError, TypeError, TimeoutError) as exc:
        print(f"modsim: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
