"""Verification of a Thing Model against a real device and its report (POLL-02a).

With ``--report`` or ``--upload`` the read executes the whole
``modpoll:acquisition`` plan once: read-only, no retries and a bounded
timeout. The result per point is recorded in a verification report whose
format and validation belong to modpoll-wot. The report holds no address,
Unit ID, serial number or value; the receiving service resolves the catalog
product from the model fingerprint, so the user never names the product.
"""

import hashlib
import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from importlib.metadata import version as package_version
from pathlib import Path

import modpoll_wot
import requests

from . import __version__
from .login import headers as api_headers

MAX_TIMEOUT = 10.0


def validate_args(args):
    """Reject option combinations a command cannot honour, before anything is connected."""
    args.full_read = args.report is not None
    if args.yes and args.upload is None and args.report is None:
        raise ValueError("--yes needs --report or --upload")
    if (args.confirm or args.reject) and not args.full_read:
        raise ValueError("--confirm and --reject need --report")
    if args.upload is not None and not args.full_read:
        # Uploading a saved report does not read a device.
        if args.mqtt_host:
            raise ValueError("An uploaded report is not published to MQTT")
        if args.export:
            raise ValueError("An uploaded report has no snapshot to export")
        return
    sources = list(args.config or [])
    if not sources:
        raise ValueError("One of --config/-f is required")
    if not args.full_read:
        return
    if args.mqtt_host:
        raise ValueError("A verification report is not published to MQTT")
    if args.udp:
        raise ValueError("A verification report supports Modbus TCP and RTU, not UDP")
    if args.serial and args.framer == "ascii":
        raise ValueError("A verification report supports Modbus RTU, not Modbus ASCII")
    if len(sources) != 1:
        raise ValueError("A verification report reads one Thing Model")
    if args.timeout > MAX_TIMEOUT:
        raise ValueError(
            f"--timeout is at most {MAX_TIMEOUT:g} seconds for a verification report"
        )
    args.once = True
    args.daemon = False


def resolve_models(args):
    """Fetch the Workspace Thing Models that are not files.

    The bytes go to ``args.model_payloads`` for the handlers, and where a
    verification model came from to ``args.model_source`` for the report.
    """
    args.model_payloads = {}
    for location in args.config or []:
        if location.startswith(modpoll_wot.REFERENCE_PREFIX):
            payload, details = fetch_workspace_model(location, timeout=args.timeout)
            args.model_payloads[location] = payload
            if args.full_read:
                args.model_source = {"source": "workspace", "ref": details["ref"]}


def fetch_workspace_model(text, *, timeout):
    """A custom Thing Model version of the user's Workspace: (bytes, {product, ref}).

    The login is used when there is one; a shared version can be read without it. The token only goes to the
    server it was issued for, and the download is checked against the SHA-256 the server states.
    """
    reference = modpoll_wot.parse_reference(text)
    server = modpoll_wot.active_server()
    session = modpoll_wot.load_session(server)
    token = session.token if session else None
    base = f"{server}/api/v1/thing-models/{reference.id}"

    def get(url):
        if not url.startswith(server + "/"):
            raise ValueError(f"{server} pointed to another address for {text}")
        try:
            return requests.get(url, headers=api_headers(token), timeout=timeout)
        except requests.RequestException as exc:
            raise ValueError(f"Could not reach {server}: {exc}") from exc

    response = get(base)
    if response.status_code == 401:
        raise ValueError("Your ModioHub login is no longer valid; run modpoll login")
    if response.status_code == 404:
        raise ValueError(
            f"No custom Thing Model {reference.id} is shared"
            + (" or yours" if token else "; run modpoll login if it is yours")
        )
    _check_server(response, server)
    thing_model = response.json()
    versions = {str(version["version"]): version for version in thing_model["versions"]}
    version = (
        versions.get(reference.version)
        if reference.version != "latest"
        else thing_model["versions"][0]
    )
    if version is None:
        raise ValueError(f"{text} has no version {reference.version}")
    response = get(version["fileUrl"])
    _check_server(response, server)
    payload = response.content
    if hashlib.sha256(payload).hexdigest() != version["sha256"]:
        raise ValueError(f"{text} does not match the SHA-256 {server} reports for it")
    return payload, {
        "product": thing_model["productId"],
        "ref": f"{reference.id}@{version['version']}",
    }


def _check_server(response, server):
    if not response.ok:
        raise ValueError(f"{server} answered {response.status_code}")


def upload_report(report, *, timeout):
    """Upload a report as the signed-in user; returns the stored report summary."""
    server = modpoll_wot.active_server()
    session = modpoll_wot.load_session(server)
    if session is None:
        raise ValueError(f"Sign in to {server} first with modpoll login")
    try:
        response = requests.post(
            f"{server}/api/v1/reports",
            json=report,
            timeout=timeout,
            headers={
                **api_headers(session.token),
                "Idempotency-Key": str(uuid.uuid4()),
            },
        )
    except requests.RequestException as exc:
        raise ValueError(f"Could not reach {server}: {exc}") from exc
    if response.status_code == 401:
        raise ValueError("Your ModioHub login is no longer valid; run modpoll login")
    if not response.ok:
        detail = (
            response.json().get("detail")
            if "json" in response.headers.get("Content-Type", "")
            else None
        )
        raise ValueError(
            f"{server} refused the report: {detail or response.status_code}"
        )
    return response.json()


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
    report = {
        "reportVersion": 4,
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
        "points": points,
    }
    modpoll_wot.validate_report(report, model=payload)
    return report


def load_report(target):
    """The verification report in a file, validated with modpoll-wot (no model bytes at hand)."""
    try:
        text = Path(target).read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"{target} cannot be read: {exc}") from exc
    try:
        report = json.loads(text)
    except ValueError as exc:
        raise ValueError(f"{target} is not JSON: {exc}") from exc
    try:
        modpoll_wot.validate_report(report)
    except modpoll_wot.ReportError as exc:
        raise ValueError(f"{target} is not a verification report: {exc}") from exc
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
