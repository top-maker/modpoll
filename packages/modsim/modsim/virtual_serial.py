"""A virtual serial cable on pseudo-terminals (Linux and macOS).

Two pseudo-terminal pairs are joined by a byte-forwarding bridge between their master
ends: the Modbus RTU server opens the slave of one pair and the client opens the slave
of the other. Pseudo-terminals ignore baud rate and parity, so nothing is simulated
beyond the bytes. Windows has no pseudo-terminals; use a virtual serial pair driver
and pass one of its ports to --serial instead.
"""

import asyncio
import contextlib
import logging
import os
import sys
from pathlib import Path
from typing import Optional

_logger = logging.getLogger(__name__)


def available() -> bool:
    return sys.platform != "win32"


class VirtualSerialPair:
    """Two joined ports: `server_port` for modsim and `client_port` for the Modbus client."""

    def __init__(self, link: Optional[str] = None) -> None:
        self.server_port = ""
        self.client_port = ""
        self._link = Path(link) if link else None
        self._masters: list[int] = []
        self._slaves: list[int] = []
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def open(self, loop: asyncio.AbstractEventLoop) -> None:
        if not available():
            raise OSError("virtual serial ports are not available on Windows")
        import pty
        import tty

        if self._link is not None and (self._link.exists() or self._link.is_symlink()):
            if not self._link.is_symlink():
                raise ValueError(f"--serial-link {self._link} exists and is not a link")
            self._link.unlink()
        self._loop = loop
        try:
            names = []
            for _ in range(2):
                master, slave = pty.openpty()
                self._masters.append(master)
                # Keep the slaves open for the life of the pair: a pseudo-terminal master
                # reports a hangup once no slave is open, e.g. between two client runs.
                self._slaves.append(slave)
                tty.setraw(slave)
                os.set_blocking(master, False)
                names.append(os.ttyname(slave))
            self.server_port, self.client_port = names
            if self._link is not None:
                self._link.symlink_to(self.client_port)
            first, second = self._masters
            loop.add_reader(first, self._forward, first, second)
            loop.add_reader(second, self._forward, second, first)
        except BaseException:
            self.close()
            raise

    def _forward(self, source: int, target: int) -> None:
        try:
            data = os.read(source, 4096)
        except (BlockingIOError, InterruptedError):
            return
        except OSError:
            assert self._loop is not None
            self._loop.remove_reader(source)
            return
        try:
            written = os.write(target, data)
        except BlockingIOError:
            written = 0
        if written < len(data):
            _logger.warning(
                "Virtual serial bridge dropped %d bytes", len(data) - written
            )

    def close(self) -> None:
        for master in self._masters:
            if self._loop is not None:
                with contextlib.suppress(Exception):
                    self._loop.remove_reader(master)
        for descriptor in (*self._masters, *self._slaves):
            with contextlib.suppress(OSError):
                os.close(descriptor)
        self._masters, self._slaves = [], []
        if self._link is not None and self._link.is_symlink():
            with contextlib.suppress(OSError):
                self._link.unlink()
