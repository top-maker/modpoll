"""A collection of utility tools"""

import argparse
import logging.config
from datetime import datetime, timezone
from typing import Any, Dict
from pymodbus.framer import (
    FramerType,
)

from . import __version__, virtual_serial

# Above 1023, so the first command needs no administrator rights.
DEFAULT_PORT = 5020

config: Dict[str, Any] = {}


def get_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=f"Modsim v{__version__} - A Simple Modbus TCP Device Simulator used for modpoll tool",
        epilog="Managed commands: up, down, ps, logs, export, reset. Use modsim COMMAND --help. Sign in to ModioHub with modsim login.",
    )
    parser.add_argument(
        "-v", "--version", action="version", version=f"{__package__} v{__version__}"
    )
    sources = parser.add_mutually_exclusive_group()
    sources.add_argument(
        "--config",
        help="Profile 0.2 TM/TD local path, HTTPS URL, or modiohub:<id>@<version> for a custom Thing Model in your ModioHub Workspace",
    )
    parser.add_argument(
        "--data",
        help=(
            "Simulation data for --config: a local path or HTTPS URL of a data "
            "document or a modpoll --export snapshot"
        ),
    )
    parser.add_argument("--script", help="Local Python behavior for --config")
    parser.add_argument(
        "--allow-scripts",
        action="store_true",
        help="Allow local Python behavior execution",
    )
    parser.add_argument("--unit-id", type=int, help="Instance Unit ID for --config")
    parser.add_argument(
        "--bind", help="Listener address; configured TCP devices default to 127.0.0.1"
    )
    parser.add_argument("--param", action="append", default=[], metavar="NAME=JSON")
    parser.add_argument(
        "--initial", action="append", default=[], metavar="PROPERTY=JSON"
    )
    parser.add_argument(
        "--comm",
        choices=["tcp", "udp", "serial", "tls"],
        help="set communication, default is tcp",
        default=None,
        type=str,
    )
    parser.add_argument(
        "--serial",
        metavar="PORT",
        help=(
            "listen for Modbus RTU on a serial port; 'pty' creates a virtual serial "
            "port (Linux, macOS) and prints the port for the client"
        ),
    )
    parser.add_argument(
        "--serial-baud", type=int, help="serial baud rate, default is 9600"
    )
    parser.add_argument(
        "--serial-parity",
        choices=["none", "even", "odd"],
        help="serial parity, default is none",
    )
    parser.add_argument(
        "--serial-link",
        metavar="PATH",
        help="with --serial pty, also create this symbolic link to the client port",
    )
    parser.add_argument(
        "--framer",
        choices=["ascii", "rtu", "socket", "tls"],
        help="set framer, default depends on --comm",
        type=str,
    )
    parser.add_argument(
        "--log",
        choices=["critical", "error", "warning", "info", "debug"],
        help="set log level, default is info",
        default="info",
        type=str,
    )
    parser.add_argument(
        "--port",
        help="set port; defaults to 5020, which needs no administrator rights",
        type=str,
    )
    parser.add_argument(
        "--store",
        choices=["sequential", "sparse", "factory", "none"],
        help="set type of datastore",
        default="sequential",
        type=str,
    )
    parser.add_argument(
        "--slaves",
        help="set number of slaves, default is 0 (any)",
        default=0,
        type=int,
        nargs="+",
    )
    parser.add_argument(
        "--context",
        help="ADVANCED USAGE: set datastore context object",
        default=None,
    )
    return parser


def get_commandline() -> argparse.Namespace:
    parser = get_parser()
    args = parser.parse_args()

    if args.serial:
        if args.comm not in (None, "serial"):
            parser.error("--serial cannot be combined with --comm %s" % args.comm)
        if args.port:
            parser.error("--serial and --port are mutually exclusive")
        args.comm = "serial"
        args.port = args.serial
    args.comm = args.comm or "tcp"
    if args.comm != "serial" and (
        args.serial_baud or args.serial_parity or args.serial_link
    ):
        parser.error(
            "--serial-baud, --serial-parity and --serial-link require --serial"
        )
    if args.serial_link and args.serial != "pty":
        parser.error("--serial-link requires --serial pty")
    if args.serial == "pty" and not virtual_serial.available():
        parser.error(
            "--serial pty is not available on Windows: create a virtual serial port "
            "pair with a driver such as com0com and pass one of its ports to --serial"
        )
    args.serial_baud = args.serial_baud or 9600
    args.serial_parity = args.serial_parity or "none"
    if not args.config and (
        args.initial
        or args.param
        or args.unit_id is not None
        or args.data
        or args.script
    ):
        parser.error(
            "--data, --initial, --param, --script and --unit-id require --config"
        )
    if args.bind and args.comm != "tcp":
        parser.error("--bind currently supports --comm tcp only")
    if args.config and args.comm not in ("tcp", "serial"):
        parser.error("model-driven simulation supports TCP and --serial")
    if args.store != "sequential":
        parser.error("only --store sequential is supported")
    if args.slaves != 0:
        parser.error(
            "--slaves is not supported; the default datastore is shared by all unit IDs"
        )
    if args.context is not None:
        parser.error("--context is not supported from the command line")
    allowed_framers = {
        "tcp": {"socket"},
        "udp": {"socket"},
        "serial": {"rtu", "ascii"},
        "tls": {"tls"},
    }
    if args.framer and args.framer not in allowed_framers[args.comm]:
        parser.error("framer %s is not supported for %s" % (args.framer, args.comm))

    # set defaults
    comm_defaults: Dict[str, list] = {
        "tcp": ["socket", DEFAULT_PORT],
        "udp": ["socket", DEFAULT_PORT],
        "serial": ["rtu", "/dev/ptyp0"],
        "tls": ["tls", DEFAULT_PORT],
    }
    framers: Dict[str, Any] = {
        "ascii": FramerType.ASCII,
        "rtu": FramerType.RTU,
        "socket": FramerType.SOCKET,
        "tls": FramerType.TLS,
    }
    args.framer = framers[args.framer or comm_defaults[args.comm][0]]
    args.port = args.port or comm_defaults[args.comm][1]
    if args.comm != "serial" and args.port:
        try:
            args.port = int(args.port)
        except ValueError:
            parser.error("port must be an integer between 1 and 65535")
        if not 1 <= args.port <= 65535:
            parser.error("port must be an integer between 1 and 65535")
    return args


def get_logger(level: str = "info") -> logging.Logger:
    if config and config.get("logging"):
        logging.config.dictConfig(config["logging"])
    else:
        logging.basicConfig(
            level=level.upper(),
            format="%(asctime)s | %(levelname).1s | %(processName)s | %(name)s | %(message)s",
        )
    logger = logging.getLogger(__name__)
    return logger


def get_utc_time() -> datetime:
    dt = datetime.now(timezone.utc)
    utc_time = dt.replace(tzinfo=timezone.utc)
    return utc_time
