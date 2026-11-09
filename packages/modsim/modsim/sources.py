"""Bounded local JSON and HTTPS model and scenario loading."""

import tempfile
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from modpoll_wot.loading import MAX_BYTES, load_document  # type: ignore[import-untyped]

from . import __version__

# Some CDNs reject the default Python-urllib agent; identify the tool instead.
USER_AGENT = f"modsim/{__version__}"


def is_remote(value: str) -> bool:
    return bool(urlparse(value).scheme) and not Path(value).is_absolute()


def local_path(base: Path, value: str) -> str:
    if urlparse(value).scheme and not Path(value).is_absolute():
        raise ValueError(f"expected local path: {value}")
    return str((base / value).resolve())


def model_document(source: str) -> dict:
    if not is_remote(source):
        return load_document(source)  # type: ignore[no-any-return]
    return remote_document(source)


def remote_document(source: str) -> dict:
    """Load bounded JSON from an HTTPS URL with the shared loader's rules."""
    url = urlparse(source)
    if url.scheme != "https":
        raise ValueError("model and scenario URLs must use HTTPS")
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
    # Reuse all bounded JSON parsing rules from the public shared loader.
    with tempfile.TemporaryDirectory(prefix="modsim-model-") as directory:
        path = Path(directory) / "model.json"
        path.write_bytes(payload)
        return load_document(path)  # type: ignore[no-any-return]
