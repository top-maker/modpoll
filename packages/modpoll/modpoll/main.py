import json
import logging
import signal
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from modpoll_wot import AcquisitionError

from .arg_parser import get_parser
from .mqtt_task import MqttHandler
from .modbus_task import (
    export_modbus_handlers,
    setup_modbus_handlers,
    snapshot_timestamp_conflicts,
)

from . import __version__, login, verification
from .utils import set_threading_event, delay_thread, on_threading_event, get_utc_time


LOG_SIMPLE = "%(asctime)s | %(levelname).1s | %(name)s | %(message)s"
logger = None


def _device_from_topic(topic_pattern, topic):
    """Match an MQTT subscription filter and return its first + level."""
    pattern_levels = topic_pattern.split("/")
    topic_levels = topic.split("/")
    device_name = None

    for index, level in enumerate(pattern_levels):
        if level == "#":
            if index != len(pattern_levels) - 1 or len(topic_levels) < index:
                return None
            return device_name
        if index >= len(topic_levels):
            return None
        if level == "+":
            if device_name is None:
                device_name = topic_levels[index]
        elif "+" in level or "#" in level or level != topic_levels[index]:
            return None

    if len(pattern_levels) != len(topic_levels):
        return None
    return device_name


def process_mqtt_command(topic, payload, retained, topic_pattern, handlers):
    """Validate and dispatch one MQTT write command without leaking input errors."""
    command_logger = logger or logging.getLogger(__name__)
    if retained:
        command_logger.warning("Ignoring retained MQTT write command on %s", topic)
        return False

    device_name = _device_from_topic(topic_pattern, topic)
    if device_name is None:
        command_logger.error("MQTT topic does not identify one device: %s", topic)
        return False

    try:
        if isinstance(payload, bytes) and len(payload) > 65536:
            raise ValueError("Payload exceeds 65536 bytes")
        command = json.loads(payload)
        if not isinstance(command, dict):
            raise ValueError("Payload must be a JSON object")
        object_type = command["object_type"]
        address = command["address"]
        value = command["value"]
        if type(address) is not int or not 0 <= address <= 65535:
            raise ValueError("Address must be an integer between 0 and 65535")
        if object_type == "coil":
            if type(value) not in (bool, int) or value not in (0, 1):
                raise ValueError("Coil value must be boolean or 0/1")
        elif object_type == "holding_register":
            if isinstance(value, list):
                if (
                    not value
                    or len(value) > 123
                    or any(
                        type(item) is not int or not 0 <= item <= 65535
                        for item in value
                    )
                    or address + len(value) > 65536
                ):
                    raise ValueError("Invalid holding register values or span")
            elif type(value) is not int or not 0 <= value <= 65535:
                raise ValueError(
                    "Register value must be an integer between 0 and 65535"
                )
        else:
            raise ValueError("Unsupported Modbus object_type")
    except (
        KeyError,
        TypeError,
        ValueError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as e:
        command_logger.warning("Ignoring invalid MQTT write command: %s", e)
        return False

    matches = [
        (handler, device)
        for handler in handlers
        for device in handler.get_device_list()
        if device.name == device_name
    ]
    if len(matches) != 1:
        command_logger.error(
            "Expected exactly one device named %s, found %d", device_name, len(matches)
        )
        return False

    handler = matches[0][0]
    if object_type == "coil":
        success = handler.write_coil(device_name, address, value)
    else:
        success = handler.write_register(device_name, address, value)
    if not success:
        command_logger.warning(
            "Failed to write %s: device=%s, address=%s, value=%s",
            object_type,
            device_name,
            address,
            value,
        )
    return success


def _ask(prompt):
    return input(prompt).strip().lower()


def _finish_full_read(args, handler):
    """Summarize the verification read, save the report, and upload it when asked.

    On a terminal without --yes the save location, the judgment of the values
    and the upload are asked interactively. The result is whether every point
    was read.
    """
    try:
        report = verification.build_report(handler, args)
    except (ValueError, OSError, AcquisitionError) as exc:
        logger.error("%s", exc)
        logger.debug("Report error details", exc_info=True)
        return False
    print(f"\n{verification.summary(report)}", flush=True)
    full = verification.is_full_read(report)
    if sys.stdin.isatty() and not args.yes:
        if not full and _ask(
            "Not every point was read, so this report does not count as a "
            "full read. Continue? [y/N] "
        ) not in ("y", "yes"):
            return False
        verdict = _ask(
            "Do the values in the table above look right? "
            "[y]es, [n]o, [Enter] not checked: "
        )
        if verdict in ("y", "yes", "n", "no"):
            # Judge only the points the device actually answered.
            judged = [
                point["property"] for point in report["points"] if point["read"] == "ok"
            ]
            if verdict in ("y", "yes"):
                args.confirm = judged
            else:
                args.reject = judged
            try:
                report = verification.build_report(handler, args)
            except (ValueError, OSError, AcquisitionError) as exc:
                logger.error("%s", exc)
                logger.debug("Report error details", exc_info=True)
                return False
    default = f"report-{datetime.now(timezone.utc).date().isoformat()}.json"
    if args.report == "":
        if args.yes:
            args.report = default  # --yes keeps the report under the default name
        elif not sys.stdin.isatty():
            logger.error("Add --report FILE when not running interactively.")
            return False
        else:
            args.report = input(f"Save the report to [{default}]: ").strip() or default
    if args.report:
        try:
            verification.write_report(report, args.report)
        except (ValueError, OSError) as exc:
            logger.error("%s", exc)
            logger.debug("Report write details", exc_info=True)
            return False
        if args.report != "-":
            print(
                f"Report written to {args.report}. It has no addresses, Unit IDs, "
                "serial numbers or values; review it before sharing.",
                flush=True,
            )
    # --report includes the upload: interactive runs ask, --yes uploads without
    # asking and therefore needs an existing sign-in.
    upload = args.upload is not None or args.yes
    confirmed = False
    if not upload and sys.stdin.isatty():
        upload = _ask("Upload this report to ModioHub? [y/N] ") in ("y", "yes")
        confirmed = upload
    if upload and not _upload(args, report, confirm=not confirmed):
        return False
    return full


def _ensure_login():
    """A session for the upload; without one, sign in with the browser right here.

    Without a terminal there is no one to approve the browser sign-in, so the
    caller gets an error instead (``--yes`` uploads require an existing login).
    """
    import modpoll_wot

    server = modpoll_wot.active_server()
    session = modpoll_wot.load_session(server)
    if session is None:
        if not sys.stdin.isatty():
            raise ValueError(
                f"Sign in to {server} first with modpoll login; "
                "an upload without questions needs an existing login."
            )
        print(f"Not signed in to {server}; starting the browser sign-in.", flush=True)
        login.login(server)
    else:
        who = f" as {session.github_user}" if session.github_user else ""
        print(f"Signed in to {server}{who}.", flush=True)


def _latest_report_file():
    """The newest report-*.json in the current directory, for the interactive --upload default."""
    candidates = sorted(
        Path.cwd().glob("report-*.json"), key=lambda path: path.stat().st_mtime
    )
    return str(candidates[-1]) if candidates else ""


def _upload_saved(args):
    """Upload a report saved earlier: choose the file, preview it, confirm, then upload."""
    target = args.upload
    if not target:
        if not sys.stdin.isatty():
            logger.error("Add --upload FILE when not running interactively.")
            return False
        default = _latest_report_file()
        prompt = "Report file to upload"
        prompt += f" [{default}]: " if default else ": "
        target = input(prompt).strip() or default
        if not target:
            logger.error("No report file given.")
            return False
    try:
        report = verification.load_report(target)
    except ValueError as exc:
        logger.error("%s", exc)
        logger.debug("Report load details", exc_info=True)
        return False
    return _upload(args, report)


def _upload(args, report, *, confirm=True):
    """Show the report and, once the user agrees, upload it. Returns whether it was uploaded.

    ``confirm`` is false when the caller already asked (a yes to the bare
    ``--report`` upload question), or with ``--yes``.
    """
    print("\nReport to upload:\n" + json.dumps(report, indent=2), flush=True)
    if confirm and not args.yes:
        if not sys.stdin.isatty():
            logger.error("Add --yes to upload without being asked.")
            return False
        if input("Upload this report to ModioHub? [y/N] ").strip().lower() not in (
            "y",
            "yes",
        ):
            print("Not uploaded.", flush=True)
            return False
    try:
        _ensure_login()
        stored = verification.upload_report(report, timeout=args.timeout)
    except (ValueError, login.LoginError, OSError) as exc:
        logger.error("%s", exc)
        return False
    print(
        "Uploaded. "
        + (
            "This is a full read and counts toward the community level."
            if stored["fullRead"]
            else "It is not a full read, so it does not count toward the community level."
        ),
        flush=True,
    )
    print("Thank you for verifying the Thing Model on real hardware.", flush=True)
    return True


def _request_exit():
    if logger:
        logger.info(f"Exiting {sys.argv[0]}")
    set_threading_event()


def _signal_handler(signal_number, frame):
    # Python runs the handler between two bytecodes of the main thread, which may hold
    # the exit event's internal (non-reentrant) lock inside delay_thread(); setting the
    # event here would then wait for that lock forever. Another thread sets it as soon
    # as the main thread lets the lock go.
    thread = threading.Thread(target=_request_exit, name="modpoll-exit", daemon=True)
    thread.start()
    return thread


def setup_logging(level, format):
    logging.basicConfig(level=level, format=format)


def app(name="modpoll"):
    if sys.argv[1:2] in (["login"], ["logout"]):
        sys.exit(login.command(sys.argv[1:]))
    mqtt_handler = None
    modbus_handlers = []

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    # parse args
    args = get_parser().parse_args()

    print(
        f"\nModpoll v{__version__} - A New Command-line Tool for Modbus and MQTT\n",
        flush=True,
    )

    # get logger
    setup_logging(args.loglevel, LOG_SIMPLE)
    global logger
    logger = logging.getLogger(__name__)

    try:
        verification.validate_args(args)
    except ValueError as exc:
        logger.error("%s", exc)
        sys.exit(2)

    if args.upload is not None and args.report is None:
        sys.exit(0 if _upload_saved(args) else 1)

    # setup mqtt
    if not args.mqtt_host:
        logger.info("No MQTT host specified, skip MQTT setup.")
    else:
        logger.info(f"Setup MQTT connection to {args.mqtt_host}:{args.mqtt_port}")
        try:
            mqtt_handler = MqttHandler(
                "MqttHandler",
                args.mqtt_host,
                args.mqtt_port,
                args.mqtt_user,
                args.mqtt_pass,
                args.mqtt_clientid,
                args.mqtt_qos,
                subscribe_topics=[args.mqtt_subscribe_topic_pattern],
                use_tls=args.mqtt_use_tls,
                tls_version=args.mqtt_tls_version,
                cacerts=args.mqtt_cacerts,
                insecure=args.mqtt_insecure,
                mqtt_version=args.mqtt_version,
                log_level=args.loglevel,
            )
            if mqtt_handler.setup() and mqtt_handler.connect():
                logger.info("Connected to MQTT broker.")
            else:
                logger.error("Failed to connect with MQTT broker, exiting...")
                try:
                    mqtt_handler.close()
                except Exception as close_err:
                    logger.debug(
                        f"Ignoring MQTT close error after failed connect: {close_err}"
                    )
                sys.exit(1)
        except Exception as e:
            logger.error(f"Error setting up MQTT input: {e}, exiting...")
            if mqtt_handler:
                try:
                    mqtt_handler.close()
                except Exception as close_err:
                    logger.debug(
                        f"Ignoring MQTT close error after setup exception: {close_err}"
                    )
            sys.exit(1)

    try:
        # setup modbus tasks
        try:
            verification.resolve_models(args)
            modbus_handlers = setup_modbus_handlers(args, mqtt_handler)
        except (ValueError, AcquisitionError) as exc:
            # A mistake in the command line or model is reported, not a stack.
            logger.error("%s", exc)
            logger.debug("Configuration error details", exc_info=True)
            sys.exit(2)
        conflicts = (
            snapshot_timestamp_conflicts(modbus_handlers or [])
            if args.export and args.timestamp
            else []
        )
        if conflicts:
            logger.error(
                "--timestamp would overwrite the point named timestamp in the "
                f"snapshot of {', '.join(conflicts)}; drop --timestamp. Exiting..."
            )
            sys.exit(1)
        if modbus_handlers:
            logger.info(f"Loaded {len(modbus_handlers)} Modbus config(s).")
            delay_thread(args.delay)
        else:
            logger.error("No Modbus config(s) defined. Exiting...")
            sys.exit(1)

        # main loop
        last_check = None
        last_diag = None
        cycle_success = True
        while not on_threading_event():
            now = get_utc_time()
            monotonic_now = time.monotonic()
            # Use a monotonic clock for scheduling; timestamps remain UTC.
            if last_check is None or monotonic_now >= last_check + args.rate:
                if last_check is None:
                    elapsed = args.rate
                else:
                    elapsed = round(monotonic_now - last_check, 6)
                last_check = monotonic_now
                logger.info(
                    f" === Modpoll is polling at rate:{args.rate}s, actual:{elapsed}s ==="
                )
                for modbus_handler in modbus_handlers:
                    modbus_handler.poll()
                    if args.once:
                        cycle_success = cycle_success and all(
                            device.pollSuccess
                            for device in modbus_handler.get_device_list()
                        )
                    if on_threading_event():
                        break
                    if args.mqtt_host:
                        if args.timestamp:
                            modbus_handler.publish_data(timestamp=now)
                        else:
                            modbus_handler.publish_data()
                if args.export and not on_threading_event():
                    export_success = export_modbus_handlers(
                        modbus_handlers,
                        args.export,
                        timestamp=now if args.timestamp else None,
                    )
                    cycle_success = export_success and cycle_success
                if args.full_read and not on_threading_event():
                    cycle_success = (
                        _finish_full_read(args, modbus_handlers[0]) and cycle_success
                    )
            if args.diagnostics_rate > 0 and (
                last_diag is None or monotonic_now >= last_diag + args.diagnostics_rate
            ):
                last_diag = monotonic_now
                for modbus_handler in modbus_handlers:
                    modbus_handler.publish_diagnostics()
            if on_threading_event():
                break
            # Check if receive mqtt request
            if mqtt_handler:
                topic, payload, retained = mqtt_handler.receive()
                if topic and payload is not None:
                    process_mqtt_command(
                        topic,
                        payload,
                        retained,
                        args.mqtt_subscribe_topic_pattern,
                        modbus_handlers,
                    )
            if args.once:
                set_threading_event()
                if not cycle_success:
                    raise SystemExit(1)
                break

            delay_thread(0.01)

    finally:
        for modbus_handler in modbus_handlers:
            try:
                modbus_handler.close()
            except Exception:
                logger.exception("Failed to close Modbus handler")
        if mqtt_handler:
            try:
                mqtt_handler.close()
            except Exception:
                logger.exception("Failed to close MQTT handler")


if __name__ == "__main__":
    app()
