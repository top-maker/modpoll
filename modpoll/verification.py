"""Full read of a Thing Model on a real device and its verification report (POLL-02a).

A full read executes the whole ``modpoll:acquisition`` plan once: read-only, no retries and a bounded timeout. The
result per point is recorded in a verification report whose format and validation belong to modpoll-wot. The report
holds no address, Unit ID, serial number or value; the user reviews it before anything leaves the machine.
"""

import base64
import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from importlib.metadata import version as package_version
from pathlib import Path

import modpoll_wot
import requests

from . import __version__

CATALOG_API = "https://api.github.com/repos/top-maker/open-modbus-catalog"
MAX_TIMEOUT = 10.0
_SLUG = r"[a-z0-9]+(?:-[a-z0-9]+)*"
_DEVICE = re.compile(rf"^({_SLUG}/{_SLUG})(?:@([A-Za-z0-9][A-Za-z0-9._/-]{{0,99}}))?$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")


def parse_device(text):
    """``manufacturer/model-number[@ref]`` as (product ID, ref); the ref is a commit, tag or branch."""
    match = _DEVICE.match(text)
    if not match:
        raise ValueError(
            "--device must be <manufacturer>/<model-number>, optionally followed by @<commit>"
        )
    return match.group(1), match.group(2) or "main"


def validate_args(args):
    """Reject option combinations a full read cannot honour, before anything is connected."""
    args.full_read = args.full_read or bool(args.report)
    if args.device and args.config:
        raise ValueError("Use either --device or -f, not both")
    if not args.device and not args.config:
        raise ValueError("One of -f or --device is required")
    if args.device:
        parse_device(args.device)
    if not args.full_read:
        for option in ("confirm", "reject", "chassis", "firmware", "configuration"):
            if getattr(args, option):
                raise ValueError(f"--{option} needs --full-read or --report")
        return
    if args.mqtt_host:
        raise ValueError("A full read does not publish to MQTT")
    if args.udp:
        raise ValueError("A full read supports Modbus TCP and RTU, not UDP")
    if args.serial and args.framer == "ascii":
        raise ValueError("A full read supports Modbus RTU, not Modbus ASCII")
    if args.device is None and args.config and len(args.config) != 1:
        raise ValueError("A full read reads one Thing Model")
    if args.report and not (args.device or args.product):
        raise ValueError(
            "--report with -f needs --product <manufacturer>/<model-number>"
        )
    if args.product and not _DEVICE.match(args.product):
        raise ValueError("--product must be <manufacturer>/<model-number>")
    if args.timeout > MAX_TIMEOUT:
        raise ValueError(f"--timeout is at most {MAX_TIMEOUT:g} seconds in a full read")
    if args.chassis and not _DEVICE.match(args.chassis):
        raise ValueError("--chassis must be <manufacturer>/<model-number>")
    args.once = True
    args.daemon = False


def git_blob_sha1(payload):
    """The id Git gives a file, so a download can be checked against the catalog repository."""
    return hashlib.sha1(b"blob %d\0" % len(payload) + payload).hexdigest()


def _github(path, *, timeout, **kwargs):
    headers = {"User-Agent": f"modpoll/{__version__}", **kwargs.pop("headers", {})}
    try:
        response = requests.get(
            f"{CATALOG_API}/{path}", headers=headers, timeout=timeout, **kwargs
        )
    except requests.RequestException as exc:
        raise ValueError(f"Could not reach the catalog on GitHub: {exc}") from exc
    return response


def fetch_catalog_model(product, ref, *, timeout):
    """The baseline Thing Model of a catalog product at a commit: (bytes, 40-character commit).

    A branch or tag is resolved to its commit first, so a report names the exact version that was read. The file
    is checked against the Git blob id GitHub reports for it.
    """
    commit = ref
    if not _COMMIT.match(ref):
        response = _github(
            f"commits/{requests.utils.quote(ref, safe='')}",
            timeout=timeout,
            headers={"Accept": "application/vnd.github.sha"},
        )
        if response.status_code in (404, 422):
            raise ValueError(f"The catalog has no commit, tag or branch {ref}")
        _check_github(response)
        commit = response.text.strip()
        if not _COMMIT.match(commit):
            raise ValueError("GitHub answered with an unexpected commit id")
    response = _github(
        f"contents/products/{product}/model.tm.json",
        timeout=timeout,
        params={"ref": commit},
    )
    if response.status_code == 404:
        raise ValueError(
            f"The catalog has no Thing Model for {product} at {commit[:7]}"
        )
    _check_github(response)
    entry = response.json()
    if entry.get("encoding") != "base64" or "content" not in entry:
        raise ValueError(
            f"The catalog's Thing Model for {product} is too large to fetch"
        )
    payload = base64.b64decode(entry["content"])
    if git_blob_sha1(payload) != entry.get("sha"):
        raise ValueError(
            f"The Thing Model for {product} does not match its Git object id"
        )
    return payload, commit


def _check_github(response):
    if (
        response.status_code == 403
        and response.headers.get("X-RateLimit-Remaining") == "0"
    ):
        raise ValueError(
            "GitHub's anonymous request limit is used up; retry in an hour or use -f"
        )
    if not response.ok:
        raise ValueError(f"GitHub answered {response.status_code}")


def resolve_models(args):
    """For ``--device``, fetch the model and name it as the configuration.

    The bytes go to ``args.model_payloads`` for the handler, and where they came from to ``args.model_source``
    for the report.
    """
    if not args.device:
        return
    product, ref = parse_device(args.device)
    payload, commit = fetch_catalog_model(product, ref, timeout=args.timeout)
    label = f"{product}@{commit[:7]}"
    args.config = [label]
    args.product = product
    args.model_payloads = {label: payload}
    args.model_source = {"source": "catalog", "ref": commit}


def _transport(args):
    return "rtu" if args.serial else "tcp"


def _points(handler):
    """(property, poller or None) for every readable property of the model, in model order."""
    pollers = {}
    for device in handler.get_device_list():
        for poller in device.pollerList:
            for point in poller.readablePoints:
                pollers[point.name] = poller
    return pollers


def build_report(handler, args):
    """The verification report of the read that just ran, checked against the model by modpoll-wot."""
    payload = handler.model_bytes
    fingerprints = modpoll_wot.point_fingerprints(payload)
    pollers = _points(handler)
    points_by_name = {
        point.name: point
        for device in handler.get_device_list()
        for point in device.points.values()
    }
    judged = (
        {name: "confirmed" for name in fingerprints} if "all" in args.confirm else {}
    )
    judged.update({name: "confirmed" for name in args.confirm if name != "all"})
    judged.update({name: "rejected" for name in args.reject})
    unknown = sorted(set(judged) - set(fingerprints))
    if unknown:
        raise ValueError(f"No readable point named {', '.join(unknown)}")
    points = []
    for name, fingerprint in fingerprints.items():
        poller = pollers.get(name)
        point = {"property": name, "fingerprint": fingerprint}
        if poller is None:
            point["read"] = "not-tested"
        elif poller.failure is not None:
            point["read"], code = poller.failure
            if code is not None:
                point["exceptionCode"] = code
        elif points_by_name[name].valid_this_poll:
            point["read"] = "ok"
        else:
            # The device answered but the answer could not be decoded as this point.
            point["read"] = "not-tested"
        read_ok = point["read"] == "ok"
        if name in judged and not read_ok:
            raise ValueError(
                f"Point {name} was not read successfully, so it cannot be confirmed or rejected"
            )
        point["expected"] = judged.get(name, "unchecked") if read_ok else "unchecked"
        points.append(point)
    environment = {
        key: value
        for key, value in (
            ("chassis", args.chassis),
            ("firmware", args.firmware),
            ("configuration", args.configuration),
        )
        if value
    }
    report = {
        "reportVersion": 3,
        "product": args.product,
        "model": {
            "sha256": hashlib.sha256(payload).hexdigest(),
            "fingerprint": modpoll_wot.model_fingerprint(payload),
            **(getattr(args, "model_source", None) or {"source": "local"}),
        },
        "tool": {
            "name": "modpoll",
            "version": __version__,
            "interpreter": package_version("modpoll-wot"),
        },
        "transport": _transport(args),
        "date": datetime.now(timezone.utc).date().isoformat(),
        **({"environment": environment} if environment else {}),
        "points": points,
    }
    modpoll_wot.validate_report(report, model=payload)
    return report


def is_full_read(report):
    """Every point read successfully; the receiving service decides coverage again from the model."""
    return all(point["read"] == "ok" for point in report["points"])


def write_report(report, target):
    """Print the report for review, or write it atomically to a file; '-' means standard output."""
    text = json.dumps(report, indent=2) + "\n"
    if target == "-":
        print(text, end="")
        return
    path = Path(target)
    fd, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            output.write(text)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def summary(report):
    ok = sum(point["read"] == "ok" for point in report["points"])
    return f"Full read: {ok} of {len(report['points'])} points read successfully."
