"""Bounded local JSON and HTTPS model and simulation data loading."""

import hashlib
import tempfile
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import modpoll_wot  # type: ignore[import-untyped]
from modpoll_wot.loading import MAX_BYTES, load_document  # type: ignore[import-untyped]

from . import __version__
from .hub import call, call_json

# Some CDNs reject the default Python-urllib agent; identify the tool instead.
USER_AGENT = f"modsim/{__version__}"


def is_remote(value: str) -> bool:
    return bool(urlparse(value).scheme) and not Path(value).is_absolute()


def local_path(base: Path, value: str) -> str:
    if urlparse(value).scheme and not Path(value).is_absolute():
        raise ValueError(f"expected local path: {value}")
    return str((base / value).resolve())


def model_document(source: str) -> dict:
    if source.startswith(modpoll_wot.REFERENCE_PREFIX):
        return workspace_document(source)
    if not is_remote(source):
        return load_document(source)  # type: ignore[no-any-return]
    return remote_document(source)


def workspace_document(text: str) -> dict:
    """A custom Thing Model version of the user's ModioHub Workspace: ``modiohub:<id>@<version>``.

    The login is used when there is one; a shared version can be read without it. The token only goes to the
    server it was issued for, and the download is checked against the SHA-256 the server states.
    """
    reference = modpoll_wot.parse_reference(text)
    server = modpoll_wot.active_server()
    session = modpoll_wot.load_session(server)
    token = session.token if session else None
    status, thing_model = call_json(
        f"{server}/api/v1/thing-models/{reference.id}", token=token
    )
    if status == 401:
        raise ValueError("Your ModioHub login is no longer valid; run modsim login")
    if status == 404:
        raise ValueError(
            f"No custom Thing Model {reference.id} is shared"
            + (" or yours" if token else "; run modsim login if it is yours")
        )
    if status != 200:
        raise ValueError(f"{server} answered {status}")
    versions = {str(item["version"]): item for item in thing_model["versions"]}
    version = (
        thing_model["versions"][0]
        if reference.version == "latest"
        else versions.get(reference.version)
    )
    if version is None:
        raise ValueError(f"{text} has no version {reference.version}")
    if not version["fileUrl"].startswith(server + "/"):
        raise ValueError(f"{server} pointed to another address for {text}")
    status, payload = call(version["fileUrl"], token=token)
    if status != 200:
        raise ValueError(f"{server} answered {status}")
    if hashlib.sha256(payload).hexdigest() != version["sha256"]:
        raise ValueError(f"{text} does not match the SHA-256 {server} reports for it")
    return _bounded_document(payload)


def remote_document(source: str) -> dict:
    """Load bounded JSON from an HTTPS URL with the shared loader's rules."""
    url = urlparse(source)
    if url.scheme != "https":
        raise ValueError("model and data URLs must use HTTPS")
    if url.hostname == "github.com":
        parts = url.path.strip("/").split("/")
        if len(parts) >= 5 and parts[2] == "blob":
            source = "https://raw.githubusercontent.com/" + "/".join(
                parts[:2] + parts[3:]
            )
    request = Request(source, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=15) as response:
        if urlparse(response.geturl()).scheme != "https":
            raise ValueError("redirect must use HTTPS")
        payload = response.read(MAX_BYTES + 1)
    if len(payload) > MAX_BYTES:
        raise ValueError(f"document exceeds {MAX_BYTES} bytes")
    return _bounded_document(payload)


def _bounded_document(payload: bytes) -> dict:
    # Reuse all bounded JSON parsing rules from the public shared loader.
    with tempfile.TemporaryDirectory(prefix="modsim-model-") as directory:
        path = Path(directory) / "model.json"
        path.write_bytes(payload)
        return load_document(path)  # type: ignore[no-any-return]
