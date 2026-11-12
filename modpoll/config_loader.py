"""Detect the configuration format from content and load devices.

``--config`` accepts the v1 CSV format and WoT TM/TD JSON side by side; the
format is detected from the content, not the file name or URL suffix. A first
non-whitespace byte of ``{`` or ``[`` selects JSON; anything else is parsed as
v1 CSV. ``--thing-model`` and ``--thing-description`` assert the JSON document
kind instead of relying on detection.
"""

import requests
from modpoll_wot import AcquisitionError, loads_model
from modpoll_wot.loading import MAX_BYTES

from .wot_config import create_devices


class ConfigUsageError(ValueError):
    """A command-line usage mistake: one error line and exit code 2."""


def load_devices(
    location,
    *,
    kind=None,
    timeout,
    unit_id=None,
    host=None,
    port=None,
    parameters=None,
    logger=None,
):
    """Load one configuration and return ``(devices, model)``.

    ``model`` is the instantiated WoT model for JSON input and ``None`` for
    CSV. ``kind`` is the asserted document kind: ``"tm"``, ``"td"`` or ``None``
    to accept either.
    """
    payload = _read_bytes(location, timeout=timeout)
    if payload.lstrip()[:1] in (b"{", b"["):
        try:
            model = loads_model(
                payload,
                source=location,
                kind=kind,
                unit_id=unit_id,
                host=host,
                port=port,
                parameters=parameters,
            )
        except AcquisitionError as exc:
            # The message is pinned with the exact modpoll-wot version.
            if kind is not None and "document kind disagrees" in str(exc):
                raise ConfigUsageError(str(exc)) from exc
            raise
        # Enforce application policy even with an older, exactly pinned wheel.
        if model.profile_version != "0.2":
            raise ValueError(
                "unsupported executable profile; expected modpoll:version '0.2'"
            )
        return create_devices(model), model
    if kind is not None:
        flag = "--thing-model" if kind == "tm" else "--thing-description"
        raise ConfigUsageError(
            f"{location}: {flag} expects a TM/TD JSON document, "
            "but the content is not JSON"
        )
    if parameters is not None:
        raise ConfigUsageError(
            f"{location}: --param requires a Thing Model; "
            "CSV configurations have no placeholders"
        )
    from .csv_config import parse_csv

    devices = parse_csv(
        payload.decode("utf-8"), source=location, unit_id=unit_id, logger=logger
    )
    return devices, None


def _read_bytes(location, *, timeout):
    """Read a local path or URL with the shared 1 MiB configuration bound."""
    if location.startswith(("http://", "https://")):
        with requests.get(location, timeout=timeout, stream=True) as response:
            response.raise_for_status()
            chunks, size = [], 0
            for chunk in response.iter_content(65536):
                size += len(chunk)
                if size > MAX_BYTES:
                    raise ValueError(f"{location}: configuration exceeds 1 MiB")
                chunks.append(chunk)
            return b"".join(chunks)
    with open(location, "rb") as stream:
        payload = stream.read(MAX_BYTES + 1)
    if len(payload) > MAX_BYTES:
        raise ValueError(f"{location}: configuration exceeds 1 MiB")
    return payload
