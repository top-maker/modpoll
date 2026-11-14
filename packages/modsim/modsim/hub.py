"""Bounded requests to ModioHub, with a tool session token when there is one."""

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from modpoll_wot import MAX_BYTES

from . import __version__

TIMEOUT = 15


def call(
    url: str, *, method: str = "GET", body: Any = None, token: str | None = None
) -> tuple[int, bytes]:
    """One request; returns the status and at most 1 MiB of the answer. An error status is a result."""
    headers = {"User-Agent": f"modsim/{__version__}", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    request = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=TIMEOUT) as response:
            return response.status, response.read(MAX_BYTES + 1)[:MAX_BYTES]
    except HTTPError as error:
        return error.code, error.read(MAX_BYTES + 1)[:MAX_BYTES]
    except (URLError, TimeoutError, OSError) as exc:
        raise ValueError(f"Could not reach {url}: {exc}") from exc


def call_json(url: str, **options: Any) -> tuple[int, dict]:
    status, payload = call(url, **options)
    try:
        document = json.loads(payload)
    except ValueError:
        document = {}
    return status, document if isinstance(document, dict) else {}
