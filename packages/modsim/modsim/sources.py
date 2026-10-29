"""Bounded local JSON and HTTPS model loading."""

import tempfile
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen

from modpoll_wot.loading import MAX_BYTES, load_document  # type: ignore[import-untyped]


def local_path(base: Path, value: str) -> str:
    if urlparse(value).scheme:
        raise ValueError(f"expected local path: {value}")
    return str((base / value).resolve())


def model_document(source: str) -> dict:
    url = urlparse(source)
    if not url.scheme:
        return load_document(source)  # type: ignore[no-any-return]
    if url.scheme != "https":
        raise ValueError("model URLs must use HTTPS")
    if url.hostname == "github.com":
        parts = url.path.strip("/").split("/")
        if len(parts) >= 5 and parts[2] == "blob":
            source = "https://raw.githubusercontent.com/" + "/".join(
                parts[:2] + parts[3:]
            )
    with urlopen(source, timeout=15) as response:
        if urlparse(response.geturl()).scheme != "https":
            raise ValueError("model redirect must use HTTPS")
        payload = response.read(MAX_BYTES + 1)
    if len(payload) > MAX_BYTES:
        raise ValueError(f"model exceeds {MAX_BYTES} bytes")
    # Reuse all bounded JSON parsing rules from the public shared loader.
    with tempfile.TemporaryDirectory(prefix="modsim-model-") as directory:
        path = Path(directory) / "model.json"
        path.write_bytes(payload)
        return load_document(path)  # type: ignore[no-any-return]
