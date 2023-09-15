"""A collection of utility tools
"""
from pymodbus.transaction import (
    ModbusAsciiFramer,
    ModbusBinaryFramer,
    ModbusRtuFramer,
    ModbusSocketFramer,
    ModbusTlsFramer,
)

args = None
config = {}

# === package version ===
# try:
#     import importlib.metadata as importlib_metadata
# except ModuleNotFoundError:
#     import importlib_metadata
# __version__ = importlib_metadata.version(__package__)
__version__ = "0.3.2"
# === package version end ===


# # === KeyboardInterrupt ===
# import sys
# import signal
# import threading
#
# event_exit = threading.Event()
# def _signal_handler(signal, frame):
#     log.info(f'Exiting {sys.argv[0]}')
#     event_exit.set()
# signal.signal(signal.SIGINT, _signal_handler)
# # === KeyboardInterrupt end ===


# === parse args ===
import argparse


def get_parser():
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


def get_commandline():
    args = get_parser().parse_args()

    # set defaults
    comm_defaults = {
        "tcp": ["socket", 5020],
        "udp": ["socket", 5020],
        "serial": ["rtu", "/dev/ptyp0"],
        "tls": ["tls", 5020],
    }
    framers = {
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


# === parse args end ===


# === config logging ===
import logging.config

if config and config.get("logging"):
    logging.config.dictConfig(config["logging"])
else:
    print("no config file found, load default settings.")
    logging.basicConfig(
        level=get_commandline().log.upper(),
        format="%(asctime)s | %(levelname).1s | %(processName)s | %(name)s | %(message)s",
    )
log = logging.getLogger(__name__)
log.info("start logging")
# === config logging end ===


# === utc time ===
from datetime import datetime
from datetime import timezone


def get_utc_time():
    dt = datetime.now(timezone.utc)
    utc_time = dt.replace(tzinfo=timezone.utc)
    return utc_time


# === end utc time ===
