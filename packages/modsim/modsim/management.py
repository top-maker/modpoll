"""Local deployment supervision and atomic device reconciliation (POSIX)."""

import asyncio
from contextlib import suppress
import hashlib
import json
import logging
import os
from pathlib import Path
import signal
import stat
import tempfile
from typing import Any

from pymodbus.datastore import ModbusDeviceContext, ModbusServerContext
from pymodbus.server import ModbusTcpServer

from .manifest import Deployment, Instance, load_deployment
from .runtime import RuntimeContext

LOG = logging.getLogger(__name__)
MAX_REQUEST = 8192


def paths(name: str) -> tuple[Path, Path, Path]:
    """Use a per-user private directory and a short, name-derived socket path."""
    if os.name != "posix":
        raise ValueError("managed commands currently require POSIX (Linux/macOS/WSL)")
    root = Path(tempfile.gettempdir()) / f"modsim-{os.getuid()}"
    root.mkdir(mode=0o700, exist_ok=True)
    info = root.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
        raise ValueError("unsafe runtime directory")
    if stat.S_IMODE(info.st_mode) != 0o700:
        raise ValueError("runtime directory must have permissions 0700")
    key = hashlib.sha256(name.encode()).hexdigest()[:24]
    return root / f"{key}.sock", root / f"{key}.lock", root / f"{key}.log"


class RuntimeManager:
    """Own live devices and their tasks; commits never yield to protocol access."""

    def __init__(self, allow_scripts: bool = False) -> None:
        self.allow_scripts = allow_scripts
        self.deployment: Deployment | None = None
        self.context = RuntimeContext([])
        self.instances: dict[str, Instance] = {}
        self.devices: dict[str, Any] = {}
        self.tasks: dict[str, asyncio.Task] = {}
        self.errors: dict[str, str] = {}
        self.lock = asyncio.Lock()

    def plan(self, desired: Deployment) -> dict:
        if self.deployment:
            if desired.path != self.deployment.path:
                raise ValueError("deployment name belongs to a different file")
            if desired.name != self.deployment.name:
                raise ValueError("deployment name cannot change")
            if (desired.bind, desired.port) != (
                self.deployment.bind,
                self.deployment.port,
            ):
                raise ValueError("listener changed; run down before up")
        added, replaced, kept = [], [], []
        for key, item in desired.instances.items():
            old = self.instances.get(key)
            if old is None:
                added.append(key)
            elif item.td["id"] != old.td["id"]:
                raise ValueError(
                    f"{key}: TD id changed; remove the device before recreating"
                )
            elif item.fingerprint != old.fingerprint:
                replaced.append(key)
            else:
                kept.append(key)
        return {
            "added": added,
            "replaced": replaced,
            "removed": sorted(self.instances.keys() - desired.instances.keys()),
            "kept": kept,
        }

    async def apply(self, desired: Deployment, dry_run: bool = False) -> dict:
        plan = self.plan(desired)
        # Only changed candidates initialize; repeated up cannot rerun live hooks.
        candidates = {
            key: desired.instances[key].build(self.allow_scripts, preview=dry_run)
            for key in plan["added"] + plan["replaced"]
        }
        if dry_run:
            return plan
        retired = [self.tasks[key] for key in plan["removed"] + plan["replaced"]]
        next_devices = {
            key: candidates[key] if key in candidates else self.devices[key]
            for key in desired.instances
        }
        next_tasks = {key: self.tasks[key] for key in plan["kept"]}
        for key, device in candidates.items():
            next_tasks[key] = asyncio.create_task(self.run_device(key, device))
        # The supported datastore operations and hooks do not suspend. Swapping
        # this registry in the same event loop is also atomic across write echoes.
        self.context.devices = {
            device.unit_id: device
            for key, device in next_devices.items()
            if key not in self.errors or key in candidates
        }
        for task in retired:
            task.cancel()
        self.instances = desired.instances
        self.devices = next_devices
        self.tasks = next_tasks
        self.errors = {
            key: self.errors[key] for key in plan["kept"] if key in self.errors
        }
        self.deployment = desired
        await asyncio.gather(*retired, return_exceptions=True)
        LOG.info("Deployment applied: %s", plan)
        return plan

    async def run_device(self, key: str, device: Any) -> None:
        try:
            await device.run()
        except Exception as exc:
            self.errors[key] = str(exc)
            # An invalid behavior must not keep serving apparently healthy data.
            self.context.devices.pop(device.unit_id, None)
            LOG.exception("Device %s failed; other devices remain online", key)

    async def reset(self, key: str) -> dict:
        if key not in self.instances:
            raise ValueError(f"unknown device: {key}")
        candidate = self.instances[key].build(self.allow_scripts)
        old = self.tasks[key]
        self.context.devices[candidate.unit_id] = candidate
        self.devices[key] = candidate
        self.tasks[key] = asyncio.create_task(self.run_device(key, candidate))
        self.errors.pop(key, None)
        old.cancel()
        await asyncio.gather(old, return_exceptions=True)
        return {"reset": key}

    def status(self) -> dict:
        return {
            "running": True,
            "name": self.deployment.name if self.deployment else None,
            "source": str(self.deployment.path) if self.deployment else None,
            "pid": os.getpid(),
            "devices": [
                {
                    "id": key,
                    "tdId": self.instances[key].td["id"],
                    "unitId": device.unit_id,
                    "state": "failed" if key in self.errors else "running",
                    "error": self.errors.get(key),
                }
                for key, device in self.devices.items()
            ],
        }

    async def close(self) -> None:
        self.context.devices = {}
        for task in self.tasks.values():
            task.cancel()
        await asyncio.gather(*self.tasks.values(), return_exceptions=True)


async def request(name: str, message: dict) -> dict:
    socket_path, _, _ = paths(name)
    reader, writer = await asyncio.wait_for(
        asyncio.open_unix_connection(str(socket_path), limit=2 * 254 * 1024 * 1024), 5
    )
    try:
        writer.write(json.dumps(message).encode() + b"\n")
        await writer.drain()
        payload = await asyncio.wait_for(reader.readline(), 60)
        if not payload:
            raise ConnectionError("management connection closed")
        response = json.loads(payload)
        if "error" in response:
            raise ValueError(response["error"])
        return response  # type: ignore[no-any-return]
    finally:
        writer.close()
        await writer.wait_closed()


async def serve(
    path: Path, allow_scripts: bool = False, *, detached: bool = False
) -> None:
    """Hold the deployment lock through listener and task shutdown."""
    import fcntl

    desired = await asyncio.to_thread(load_deployment, path)
    socket_path, lock_path, log_path = paths(desired.name)
    with lock_path.open("a") as lease:
        try:
            fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError(
                "deployment is already starting or running; retry up"
            ) from exc
        manager = RuntimeManager(allow_scripts)
        stop = asyncio.Event()
        server: Any = ModbusTcpServer(
            context=ModbusServerContext(devices=ModbusDeviceContext(), single=True),
            address=(desired.bind, desired.port),
        )
        server.context = manager.context
        control = None
        handlers: set[asyncio.Task] = set()
        loop = asyncio.get_running_loop()
        signals = []
        file_handler = None
        if not detached:
            file_handler = logging.FileHandler(log_path)
            os.chmod(log_path, 0o600)
            logging.getLogger().addHandler(file_handler)

        async def handle(
            reader: asyncio.StreamReader, writer: asyncio.StreamWriter
        ) -> None:
            task = asyncio.current_task()
            if task is not None:
                handlers.add(task)
            try:
                async with manager.lock:
                    payload = await asyncio.wait_for(reader.readline(), 5)
                    message = json.loads(payload)
                    if message.get("source") != str(desired.path):
                        raise ValueError("deployment name belongs to a different file")
                    action = message.get("action")
                    if action == "up":
                        if message.get("allow_scripts") and not manager.allow_scripts:
                            raise ValueError(
                                "script permission requires down, then up --allow-scripts"
                            )
                        candidate = await asyncio.to_thread(
                            load_deployment, desired.path
                        )
                        result = await manager.apply(
                            candidate, bool(message.get("dry_run"))
                        )
                    elif action == "ps":
                        result = manager.status()
                    elif action == "reset":
                        result = await manager.reset(message.get("device", ""))
                    elif action == "export":
                        result = {
                            "tds": {
                                key: item.td for key, item in manager.instances.items()
                            }
                        }
                    elif action == "down":
                        result = {"stopping": True}
                        stop.set()
                    else:
                        raise ValueError("unknown management action")
                response = result
            except Exception as exc:
                response = {"error": str(exc)}
            try:
                writer.write(json.dumps(response).encode() + b"\n")
                await writer.drain()
            finally:
                writer.close()
                with suppress(ConnectionError):
                    await writer.wait_closed()
                if task is not None:
                    handlers.discard(task)

        try:
            await manager.apply(desired)
            if not await server.listen():
                raise OSError(f"cannot listen on {desired.bind}:{desired.port}")
            # The lease proves that a leftover socket cannot belong to a live owner.
            socket_path.unlink(missing_ok=True)
            control = await asyncio.start_unix_server(
                handle, path=str(socket_path), limit=MAX_REQUEST
            )
            os.chmod(socket_path, 0o600)
            for signum in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(signum, stop.set)
                signals.append(signum)
            LOG.info(
                "Deployment %s ready at %s:%s", desired.name, desired.bind, desired.port
            )
            await stop.wait()
        finally:
            if control:
                control.close()
                await control.wait_closed()
            for task in list(handlers):
                task.cancel()
            await asyncio.gather(*handlers, return_exceptions=True)
            for signum in signals:
                loop.remove_signal_handler(signum)
            await manager.close()
            await server.shutdown()
            socket_path.unlink(missing_ok=True)
            if file_handler:
                logging.getLogger().removeHandler(file_handler)
                file_handler.close()
