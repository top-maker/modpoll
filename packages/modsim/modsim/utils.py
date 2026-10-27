"""A collection of utility tools"""

import argparse
import logging.config
from datetime import datetime, timezone
from typing import Any, Dict
from pymodbus.transaction import (
    ModbusAsciiFramer,
    ModbusBinaryFramer,
    ModbusRtuFramer,
    ModbusSocketFramer,
    ModbusTlsFramer,
)

from . import __version__

config: Dict[str, Any] = {}


def get_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=f"Modsim v{__version__} - A Simple Modbus TCP Device Simulator used for modpoll tool"
    )
    parser.add_argument(
        "-v", "--version", action="version", version=f"{__package__} v{__version__}"
    )
    parser.add_argument(
        "--comm",
        choices=["tcp", "udp", "serial", "tls"],
        help="set communication, default is tcp",
        default="tcp",
        type=str,
    )
    parser.add_argument(
        "--framer",
        choices=["ascii", "binary", "rtu", "socket", "tls"],
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
        help="set port",
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
        "serial": {"rtu", "ascii", "binary"},
        "tls": {"tls"},
    }
    if args.framer and args.framer not in allowed_framers[args.comm]:
        parser.error("framer %s is not supported for %s" % (args.framer, args.comm))

    # set defaults
    comm_defaults: Dict[str, list] = {
        "tcp": ["socket", 5020],
        "udp": ["socket", 5020],
        "serial": ["rtu", "/dev/ptyp0"],
        "tls": ["tls", 5020],
    }
    framers: Dict[str, Any] = {
        "ascii": ModbusAsciiFramer,
        "binary": ModbusBinaryFramer,
        "rtu": ModbusRtuFramer,
        "socket": ModbusSocketFramer,
        "tls": ModbusTlsFramer,
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
