"""Bounded, read-only identity and status sampling."""

from copy import copy
from dataclasses import replace
import json

from modpoll_wot import parse_parameters

from .modbus_task import _create_modbus_client
from .wot_config import create_devices, read_model

MAX_SAMPLES = 16
MAX_TIMEOUT = 5


def run_audit(args):
    if len(args.config) != 1 or args.mqtt_host or args.export or args.daemon:
        raise ValueError(
            "--audit requires one configuration and no MQTT, export or daemon"
        )
    if args.udp or args.framer not in ("default", "rtu" if args.serial else "socket"):
        raise ValueError("--audit supports Modbus TCP and serial RTU")
    if not 0 < args.timeout <= MAX_TIMEOUT:
        raise ValueError("--audit timeout must be between 0 and 5 seconds")
    if args.serial and args.serial_baud <= 0:
        raise ValueError("--audit serial baud rate must be positive")
    model = read_model(
        args.config[0],
        timeout=args.timeout,
        unit_id=args.unit_id,
        host=args.tcp,
        port=args.tcp_port,
        parameters=parse_parameters(args.param),
    )
    plan = getattr(model, "audit", None)
    if plan is None:
        raise ValueError("--audit requires a modpoll:audit plan")
    names = plan.identity + plan.status
    if len(names) > MAX_SAMPLES:
        raise ValueError(f"--audit supports at most {MAX_SAMPLES} points")

    selected = {}
    for group in model.groups:
        for member in group.members:
            if member.property in names:
                selected[member.property] = replace(
                    group,
                    start=group.start + member.offset,
                    quantity=member.bit_count if member.physical_bits else member.width,
                    members=(replace(member, offset=0, writable=False),),
                )
    (device,) = create_devices(replace(model, groups=tuple(selected[n] for n in names)))
    connection = copy(args)
    if model.endpoint:
        if args.serial:
            raise ValueError("--audit requires an unbound TM for serial RTU")
        connection.tcp, connection.tcp_port = model.endpoint

    client = _create_modbus_client(connection)
    result = {"identity": [], "status": []}
    success = True
    try:
        connected = client.connect()
        for index, poller in enumerate(device.pollerList):
            (point,) = poller.readablePoints
            ok = connected and poller.poll(client) and point.valid_this_poll
            success = success and ok
            section = "identity" if index < len(plan.identity) else "status"
            result[section].append(
                {
                    "property": point.name,
                    "result": "read" if ok else "failed" if connected else "not-tested",
                    "value": point.val if ok else None,
                    "unit": point.unit,
                }
            )
    finally:
        client.close()
    if not plan.identity:
        result["identity_result"] = "not-provided"
    elif all(row["result"] == "read" for row in result["identity"]):
        result["identity_result"] = "sampled"
    else:
        result["identity_result"] = "incomplete"
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    return 0 if success else 1
