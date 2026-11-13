"""Detect the configuration format from content and load devices.

``--config`` accepts the v1 CSV format and WoT TM/TD JSON side by side; the
format is detected from the content, not the file name or URL suffix. A first
non-whitespace byte of ``{`` or ``[`` selects JSON; anything else is parsed as
v1 CSV. ``kind`` lets a caller assert the JSON document kind; the CLI relies
on detection instead.
"""

from modpoll_wot import AcquisitionError, loads_model

from .wot_config import create_devices, read_payload


class ConfigUsageError(ValueError):
    """A command-line usage mistake: one error line and exit code 2."""


def load_devices(
    location,
    *,
    kind=None,
    payload=None,
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
    to accept either. ``payload`` are the exact bytes when the caller already
    has them; otherwise they are read from ``location``.
    """
    if payload is None:
        payload = read_payload(location, timeout=timeout)
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
        document = "Thing Model" if kind == "tm" else "Thing Description"
        raise ConfigUsageError(
            f"{location}: expected a {document} JSON document, "
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
