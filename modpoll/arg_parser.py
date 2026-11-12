import argparse

from . import __version__
from .precision import parse_precision


def _precision(text):
    """Argparse type for --precision: 'auto' or a non-negative count."""
    try:
        return parse_precision(text)
    except ValueError as e:
        raise argparse.ArgumentTypeError(str(e)) from e


def get_parser():
    parser = argparse.ArgumentParser(
        description=f"Modpoll v{__version__} - A New Command-line Tool for Modbus and MQTT"
    )
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"v{__version__}",
    )
    parser.add_argument(
        "-f",
        "--config",
        dest="config",
        default=None,
        help=(
            "Local path or URL of a v1 CSV or WoT TM/TD JSON configuration, or "
            "modiohub:<id>@<version> for a custom Thing Model in your ModioHub "
            "Workspace (run modpoll login first unless it is shared). "
            "The format is detected from the content, not the filename. "
            "Required unless --device is given."
        ),
        nargs="+",
    )
    verification = parser.add_argument_group(
        "verification",
        "modpoll verify --config MODEL --tcp HOST reads every point of one Thing "
        "Model once, read-only and without retries, and reports which points "
        "could be read",
    )
    verification.add_argument(
        "--report",
        metavar="FILE",
        help=(
            "Write the verification report to FILE ('-' prints it). "
            "It lists each point's result and carries no address, Unit ID, serial "
            "number or value; review it before sharing."
        ),
    )
    verification.add_argument(
        "--upload",
        action="store_true",
        help=(
            "After the verification read, show the report and, once you confirm, "
            "upload it to ModioHub (run modpoll login first)"
        ),
    )
    verification.add_argument(
        "--yes",
        action="store_true",
        help="Upload without asking for confirmation after the report is shown",
    )
    verification.add_argument(
        "--product",
        metavar="MANUFACTURER/MODEL",
        help="Catalog product ID the report is for; needed when the model does not name one",
    )
    verification.add_argument(
        "--confirm",
        nargs="+",
        default=[],
        metavar="POINT",
        help="Points whose values you checked and found right ('all' for every point), for the report",
    )
    verification.add_argument(
        "--reject",
        nargs="+",
        default=[],
        metavar="POINT",
        help="Points whose values you checked and found wrong, for the report",
    )
    parser.add_argument(
        "--param",
        action="append",
        default=[],
        metavar="NAME=JSON",
        help="Typed TM placeholder binding (requires the profile 0.2 interpreter)",
    )
    parser.add_argument(
        "--unit-id",
        type=int,
        default=None,
        help="Override instance Unit ID (1-254); otherwise use the TD, the legacy CSV default, or 1",
    )
    parser.add_argument(
        "-d",
        "--daemon",
        action="store_true",
        help="Run in daemon mode without printing result. Recommended to use with docker",
    )
    parser.add_argument(
        "-r",
        "--rate",
        type=float,
        default=10.0,
        help="The sampling rate (s) to poll modbus device, Defaults to 10.0",
    )
    parser.add_argument(
        "-1", "--once", action="store_true", help="Only run polling at one time"
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=0.5,
        help="The time interval in seconds between two polling, Defaults to 0.5",
    )
    parser.add_argument(
        "--tcp",
        help="Explicit TCP host; a profile 0.2 TD uses its endpoint when omitted",
    )
    parser.add_argument(
        "--tcp-port",
        type=int,
        default=None,
        help="Port for MODBUS TCP. Defaults to 502",
    )
    parser.add_argument(
        "--udp", help="Act as a Modbus UDP master, connecting to host UDP"
    )
    parser.add_argument(
        "--udp-port", type=int, default=502, help="Port for MODBUS UDP. Defaults to 502"
    )
    parser.add_argument(
        "--serial",
        "--rtu",
        dest="serial",
        help="pyserial URL (or port name) for serial transport (alias: --rtu)",
    )
    parser.add_argument(
        "--serial-baud",
        "--rtu-baud",
        dest="serial_baud",
        type=int,
        default=9600,
        help="Baud rate for serial port. Defaults to 9600",
    )
    parser.add_argument(
        "--serial-parity",
        "--rtu-parity",
        dest="serial_parity",
        choices=["none", "odd", "even"],
        default="none",
        help="Parity for serial port. Defaults to none",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=3.0,
        help="Response time-out seconds for MODBUS devices, Defaults to 3.0",
    )
    parser.add_argument(
        "-o",
        "--export",
        default=None,
        help="The file name to export point values",
    )
    parser.add_argument(
        "--precision",
        type=_precision,
        default=None,
        metavar="auto|N",
        help=(
            "Decimals to show for float values. The default 'auto' keeps the "
            "precision of the source data; N rounds every float to at most "
            "that many decimals."
        ),
    )
    parser.add_argument(
        "--mqtt-version",
        choices=["3.1.1", "5.0"],
        default="3.1.1",
        help="MQTT version. Defaults to MQTT v3.1.1",
    )
    parser.add_argument(
        "--mqtt-host",
        default=None,
        help="MQTT server address. Skip MQTT setup if not specified",
    )
    parser.add_argument(
        "--mqtt-port",
        type=int,
        default=1883,
        help="1883 for non-TLS or 8883 for TLS, Defaults to 1883",
    )
    parser.add_argument(
        "--mqtt-clientid",
        default=None,
        help="MQTT client name, If qos > 0, set unique name for multiple clients",
    )
    parser.add_argument(
        "--mqtt-publish-topic-pattern",
        default="modpoll/{{device_name}}/data",
        help='Topic pattern for MQTT publish. Use {{device_name}} as placeholder for the device names in Modbus config. Defaults to "modpoll/{{device_name}}/data"',
    )
    parser.add_argument(
        "--mqtt-subscribe-topic-pattern",
        default="modpoll/+/set",
        help='Topic pattern for MQTT subscribe. Defaults to "modpoll/+/set"',
    )
    parser.add_argument(
        "--mqtt-diagnostics-topic-pattern",
        default="modpoll/{{device_name}}/diagnostics",
        help="Topic pattern for MQTT diagnostics. Use {{device_name}} as placeholder for the device names in Modbus config. Defaults to modpoll/{{device_name}}/diagnostics",
    )
    parser.add_argument(
        "--mqtt-qos",
        choices=[0, 1, 2],
        type=int,
        default=0,
        help="MQTT QoS value. Defaults to 0",
    )
    parser.add_argument(
        "--mqtt-user", default=None, help="Username for authentication (optional)"
    )
    parser.add_argument(
        "--mqtt-pass", default=None, help="Password for authentication (optional)"
    )
    parser.add_argument("--mqtt-use-tls", action="store_true", help="Use TLS")
    parser.add_argument(
        "--mqtt-insecure",
        action="store_true",
        help="Use TLS without providing certificates",
    )
    parser.add_argument("--mqtt-cacerts", default=None, help="Path to ca keychain")
    parser.add_argument(
        "--mqtt-tls-version",
        choices=["tlsv1.2", "tlsv1.1", "tlsv1"],
        default="tlsv1.2",
        help="TLS protocol version, can be one of tlsv1.2 tlsv1.1 or tlsv1",
    )
    parser.add_argument(
        "--mqtt-single",
        action="store_true",
        help="Publish each value in a single topic. If not specified, groups all values in one topic.",
    )
    parser.add_argument(
        "--diagnostics-rate",
        type=float,
        default=0,
        help="Time in seconds as publishing period for each device diagnostics",
    )
    parser.add_argument(
        "--autoremove",
        action="store_true",
        help="Automatically remove poller if modbus communication has failed 3 times.",
    )
    parser.add_argument(
        "--loglevel",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="INFO",
        help="Set log level, Defaults to INFO",
    )
    parser.add_argument(
        "--timestamp", action="store_true", help="Add timestamp to the result"
    )
    parser.add_argument(
        "--delay",
        type=int,
        default=0,
        help="Time to delay sending first request in seconds after connecting. Default to 0",
    )
    parser.add_argument(
        "--framer",
        default="default",
        choices=["default", "ascii", "rtu", "socket"],
        help="The type of framer for Modbus messages. Serial supports ascii/rtu; TCP/UDP use socket.",
    )
    return parser
