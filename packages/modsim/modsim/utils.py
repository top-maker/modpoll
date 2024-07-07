"""A collection of utility tools
"""

import argparse
import logging.config
from datetime import datetime, timezone
import importlib.metadata as metadata  # For Python 3.8+
from typing import Any, Optional, Dict
from pymodbus.transaction import (
    ModbusAsciiFramer,
    ModbusBinaryFramer,
    ModbusRtuFramer,
    ModbusSocketFramer,
    ModbusTlsFramer,
)

# global
args: Optional[argparse.Namespace] = None
config: Dict[str, Any] = {}


def get_version() -> str:
    try:
        return metadata.version(__package__)
    except metadata.PackageNotFoundError:
        return "unknown"


__version__ = get_version()


def get_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=f"{__package__} v{__version__} - My python app template"
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
    args = get_parser().parse_args()

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
        args.port = int(args.port)
    return args


def get_logger() -> logging.Logger:
    if config and config.get("logging"):
        logging.config.dictConfig(config["logging"])
    else:
        print("no config file found, load default settings.")
        logging.basicConfig(
            level=get_commandline().log.upper(),
            format="%(asctime)s | %(levelname).1s | %(processName)s | %(name)s | %(message)s",
        )
    logger = logging.getLogger(__name__)
    logger.info("start logging")
    return logger


def get_utc_time() -> datetime:
    dt = datetime.now(timezone.utc)
    utc_time = dt.replace(tzinfo=timezone.utc)
    return utc_time
