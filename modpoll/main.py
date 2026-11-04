import json
import logging
import signal
import sys
import time

from .arg_parser import get_parser
from .mqtt_task import MqttHandler
from .modbus_task import export_modbus_handlers, setup_modbus_handlers

from . import __version__
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


def _signal_handler(signal_number, frame):
    if logger:
        logger.info(f"Exiting {sys.argv[0]}")
    set_threading_event()


def setup_logging(level, format):
    logging.basicConfig(level=level, format=format)


def app(name="modpoll"):
    mqtt_handler = None
    modbus_handlers = []

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    # parse args
    args = get_parser().parse_args()

    if args.audit:
        from pymodbus.exceptions import ModbusException

        from .audit import run_audit

        try:
            status = run_audit(args)
        except (ValueError, OSError, ModbusException) as exc:
            print(f"Audit failed: {exc}", file=sys.stderr)
            status = 1
        raise SystemExit(status)

    print(
        f"\nModpoll v{__version__} - A New Command-line Tool for Modbus and MQTT\n",
        flush=True,
    )

    # get logger
    setup_logging(args.loglevel, LOG_SIMPLE)
    global logger
    logger = logging.getLogger(__name__)

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
                exit(1)
        except Exception as e:
            logger.error(f"Error setting up MQTT input: {e}, exiting...")
            if mqtt_handler:
                try:
                    mqtt_handler.close()
                except Exception as close_err:
                    logger.debug(
                        f"Ignoring MQTT close error after setup exception: {close_err}"
                    )
            exit(1)

    try:
        # setup modbus tasks
        modbus_handlers = setup_modbus_handlers(args, mqtt_handler)
        if modbus_handlers:
            logger.info(f"Loaded {len(modbus_handlers)} Modbus config(s).")
            delay_thread(args.delay)
        else:
            logger.error("No Modbus config(s) defined. Exiting...")
            exit(1)

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
