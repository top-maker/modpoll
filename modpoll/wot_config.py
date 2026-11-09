"""Adapt validated WoT configuration to the existing Modpoll execution engine."""

from modpoll_wot.loading import load_model, loads_model, MAX_BYTES
import requests


def read_model(location, *, timeout, unit_id, host=None, port=None, parameters=None):
    instance = {"host": host, "port": port, "parameters": parameters}
    if location.startswith(("http://", "https://")):
        with requests.get(location, timeout=timeout, stream=True) as response:
            response.raise_for_status()
            chunks, size = [], 0
            for chunk in response.iter_content(65536):
                size += len(chunk)
                if size > MAX_BYTES:
                    raise ValueError(f"{location}: configuration exceeds 1 MiB")
                chunks.append(chunk)
        model = loads_model(
            b"".join(chunks), source=location, unit_id=unit_id, **instance
        )
    else:
        model = load_model(location, unit_id=unit_id, **instance)
    # Enforce application policy even with an older, exactly pinned wheel.
    if model.profile_version != "0.2":
        raise ValueError(
            "unsupported executable profile; expected modpoll:version '0.2'"
        )
    return model


def create_devices(model):
    # The shared interpreter has no dependency on the application or PyModbus.
    from .modbus_task import Device, Poller, Point

    device = Device(model.title, model.unit_id)
    function_codes = {
        "coil": 1,
        "discrete_input": 2,
        "holding_register": 3,
        "input_register": 4,
    }
    for group in model.groups:
        poller = Poller(
            device,
            function_codes[group.table],
            group.start,
            group.quantity,
            group.byte_order,
        )
        for member in group.members:
            address = str(group.start + member.offset)
            if member.bit is not None:
                address += ":" + str(member.bit)
            access = ("r" if member.readable else "") + ("w" if member.writable else "")
            point = Point(
                device,
                member.property,
                address,
                member.data_type,
                access,
                member.unit,
                None if member.multiplier is None else float(member.multiplier),
            )
            point.endian = member.byte_order
            point.physical_bits = member.physical_bits
            point.bit_count = member.bit_count
            point.scalar = member.scalar
            if member.readable:
                poller.add_readable_point(point)
            device.add_point_mapping(point)
        device.pollerList.append(poller)
    return [device]
