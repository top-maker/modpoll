"""Verification of a Thing Model against a real device and its report (POLL-02a, POLL-06).

With ``--report`` or ``--upload`` the read executes the whole
``modpoll:acquisition`` plan once: read-only, no retries and a bounded
timeout. The result per point is recorded in a verification report whose
format and validation belong to modpoll-wot. The report holds no address,
Unit ID, serial number or value. Failures are reported as the device
answered them, and only a full read whose identity points match can be
uploaded; modpoll neither diagnoses nor changes the configuration.
"""

import hashlib
import json
import os
import tempfile
import urllib.parse
import uuid
from datetime import datetime, timezone
from importlib.metadata import version as package_version
from pathlib import Path

import modpoll_wot
import requests

from . import __version__
from .login import headers as api_headers

MAX_TIMEOUT = 10.0
CATALOG_ISSUES = "https://github.com/top-maker/open-modbus-catalog/issues/new"

TABLES = {
    1: "coils",
    2: "discrete inputs",
    3: "holding registers",
    4: "input registers",
}
# Exception names as the Modbus Application Protocol specification gives them.
EXCEPTIONS = {
    1: "illegal function",
    2: "illegal data address",
    3: "illegal data value",
    4: "server device failure",
    5: "acknowledge",
    6: "server device busy",
    8: "memory parity error",
    10: "gateway path unavailable",
    11: "gateway target device failed to respond",
}
# What each refusal of the upload means, by the problem code ModioHub answers with.
REFUSALS = {
    "not-full-read": "Not every point was read; only a full read can be uploaded.",
    "identity-mismatch": "An identity point does not match the Thing Model, so the device may be a different product.",
    "identity-missing": "This product has identity points that the report does not include. "
    "Read them together with the other points.",
    "unknown-product": "The report does not match a catalog product.",
    "unknown-model": "The report does not match a catalog product.",
    "duplicate-point": "The report is damaged or was edited by hand. Read the device again.",
    "fingerprint-mismatch": "The report is damaged or was edited by hand. Read the device again.",
}


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
                args.model_product = details["product"]


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
        body = (
            response.json()
            if "json" in response.headers.get("Content-Type", "")
            else {}
        )
        code = body.get("code")
        message = REFUSALS.get(code) or body.get("detail") or response.status_code
        if code in ("unknown-product", "unknown-model"):
            message = f"{message} Request the product in the catalog: {catalog_request(report)}"
        raise ValueError(f"{server} refused the report: {message}")
    return response.json()


def _api(method, path, *, timeout, **kwargs):
    """A call to the public ModioHub API: (server, decoded JSON)."""
    server = modpoll_wot.active_server()
    try:
        response = requests.request(
            method,
            f"{server}/api/v1{path}",
            timeout=timeout,
            headers=api_headers(None),
            **kwargs,
        )
    except requests.RequestException as exc:
        raise ValueError(f"Could not reach {server}: {exc}") from exc
    _check_server(response, server)
    return response.json()


def matched_products(report, *, timeout):
    """Catalog products whose baseline Thing Models share point fingerprints with the report.

    Each is {productId, matched, readablePoints, exact}, the closest first.
    """
    fingerprints = [point["fingerprint"] for point in report["points"]]
    return _api(
        "POST", "/products/match", timeout=timeout, json={"fingerprints": fingerprints}
    )


def search_products(text, *, timeout):
    """Catalog products whose model number, alias or manufacturer matches the text: [(id, label)]."""
    found = _api("GET", "/products", timeout=timeout, params={"q": text, "limit": 5})
    return [
        (item["id"], f"{item['modelNumber']} ({item['manufacturer']['name']['en']})")
        for item in found["items"]
    ]


def catalog_request(report):
    """A prefilled catalog issue for a product the catalog does not have; no values or addresses."""
    body = (
        "A verification report matches no catalog product.\n\n"
        f"- Model fingerprint: `{report['model']['fingerprint']}`\n"
        f"- Points: {len(report['points'])}\n"
        f"- Tool: {report['tool']['name']} {report['tool']['version']}\n\n"
        "Attach the report file and name the product and its documents."
    )
    query = urllib.parse.urlencode(
        {"template": "product-feedback.md", "title": "Product request", "body": body}
    )
    return f"{CATALOG_ISSUES}?{query}"


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
    constants = modpoll_wot.identity_constants(payload)
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
        if read_ok and name in constants:
            point["identity"] = modpoll_wot.identity_result(
                constants[name], points_by_name[name].val
            )
        points.append(point)
    product = getattr(args, "model_product", None)
    report = {
        "reportVersion": modpoll_wot.REPORT_VERSION,
        **({"product": product} if product else {}),
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


def refusal(report):
    """Why this report cannot be uploaded, or None: ModioHub accepts only schema 5 full reads that match."""
    if report["reportVersion"] != modpoll_wot.REPORT_VERSION:
        return (
            f"This report was written by an older modpoll (report version {report['reportVersion']}). "
            "Update modpoll and read the device again."
        )
    if not is_full_read(report):
        ok = sum(point["read"] == "ok" for point in report["points"])
        return (
            f"Not a full read: {ok} of {len(report['points'])} points were read. "
            "Only a full read can be uploaded."
        )
    mismatched = [
        p["property"] for p in report["points"] if p.get("identity") == "mismatch"
    ]
    if mismatched:
        return (
            f"Identity point {', '.join(mismatched)} does not match the Thing Model, "
            "so the device may be a different product. The report cannot be uploaded."
        )
    return None


def _span(poller):
    last = poller.start_address + poller.size - 1
    addresses = (
        f"{poller.start_address}-{last}" if last > poller.start_address else str(last)
    )
    return f"{TABLES[poller.fc]} {addresses}"


def failure_lines(handler):
    """What went wrong in the read, as the device answered, one line per group or point.

    Groups are numbered in ``modpoll:acquisition`` order from 1, with the
    zero-based addresses of the Thing Model. Nothing is inferred about why.
    """
    lines = []
    for device in handler.get_device_list():
        pollers = device.pollerList
        total = len(pollers)
        skipped = [index for index, poller in enumerate(pollers, 1) if poller.skipped]
        for index, poller in enumerate(pollers, 1):
            where = f"Group {index} of {total} ({_span(poller)})"
            if poller.failure is not None:
                kind, code = poller.failure
                if kind == "exception":
                    name = EXCEPTIONS.get(code)
                    lines.append(
                        f"{where}: exception code {code:02X}"
                        + (f" ({name})." if name else ".")
                    )
                else:
                    lines.append(f"{where}: no response.")
            elif not poller.skipped:
                lines.extend(
                    f"Point {point.name} (group {index}): the answer could not be decoded as {point.dtype}."
                    for point in poller.readablePoints
                    if not point.valid_this_poll
                )
        if skipped:
            first, last = skipped[0], skipped[-1]
            groups = f"Group {first}" if first == last else f"Groups {first}-{last}"
            lines.append(f"{groups} of {total}: not tried.")
    return lines


def identity_lines(handler, report):
    """The identity points that did not match: the value read and the value the Thing Model gives."""
    constants = modpoll_wot.identity_constants(handler.model_bytes)
    values = {
        point.name: point.val
        for device in handler.get_device_list()
        for point in device.points.values()
    }
    return [
        f"Identity point {p['property']}: read {values[p['property']]!r}, "
        f"the Thing Model expects {constants[p['property']]!r}."
        for p in report["points"]
        if p.get("identity") == "mismatch"
    ]


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
    total = len(report["points"])
    if ok == total:
        return f"Full read: all {total} points read."
    return f"Not a full read: {ok} of {total} points read."
