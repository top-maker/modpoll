"""Validated concrete Modbus TCP endpoints shared by model instantiation."""

import ipaddress
import re
from urllib.parse import urlsplit, parse_qs
from .acquisition import AcquisitionError


def _authority(host, port):
    if type(port) is not int or not 1 <= port <= 65535:
        raise AcquisitionError("port: expected integer between 1 and 65535")
    if not isinstance(host, str) or not host:
        raise AcquisitionError("host: required for a TM")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        if len(host) > 253 or not all(
            re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label)
            for label in host.split(".")
        ):
            raise AcquisitionError("host: expected an IP address or DNS hostname")
    else:
        if address.is_unspecified or address.is_multicast:
            raise AcquisitionError(
                "host: a listening wildcard/multicast is not an endpoint"
            )
        host = str(address)
        if "%" in host:
            raise AcquisitionError("scoped IPv6 endpoints are not supported")
        if address.version == 6:
            host = f"[{host}]"
    return f"{host.lower()}:{port}"


def _td_endpoint(form, path):
    try:
        url = urlsplit(form["href"])
        parts = url.path.strip("/").split("/")
        unit, address = map(int, parts)
        query = parse_qs(url.query, strict_parsing=True, keep_blank_values=True)
        if set(query) - {"quantity"} or len(query.get("quantity", [])) > 1:
            raise ValueError()
        quantity = int(query.get("quantity", ["1"])[0])
        if url.scheme != "modbus+tcp" or url.username or url.password or url.fragment:
            raise ValueError()
        authority = _authority(url.hostname, 502 if url.port is None else url.port)
        if not 1 <= unit <= 254:
            raise ValueError()
    except (KeyError, TypeError, ValueError) as exc:
        raise AcquisitionError(f"{path}: invalid concrete Modbus TCP href") from exc
    return authority, unit, address, quantity
