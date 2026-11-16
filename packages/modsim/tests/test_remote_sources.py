"""HTTPS model and simulation data sources."""

from io import BytesIO
import json
from unittest.mock import patch

import pytest

from modpoll_wot import load_simulation_data

from modsim import __version__, deployment, hub, sources


class Response(BytesIO):
    def __init__(self, payload, url="https://example.invalid/file.json"):
        super().__init__(payload)
        self.url = url

    def geturl(self):
        return self.url


def test_remote_documents_identify_modsim():
    payload = json.dumps({"version": "1", "tick": 0.5}).encode()
    with patch.object(sources, "urlopen", return_value=Response(payload)) as remote:
        data = deployment.data_document("https://example.invalid/device.data.json")
    assert data == {"version": "1", "tick": 0.5}
    request = remote.call_args.args[0]
    assert request.full_url == "https://example.invalid/device.data.json"
    assert request.get_header("User-agent") == hub.USER_AGENT
    assert (
        hub.USER_AGENT
        == f"modsim/{__version__} (+https://github.com/top-maker/modpoll)"
    )
    assert sources.USER_AGENT is hub.USER_AGENT  # one construction for every request


def test_simulation_data_rejects_scripts_and_plain_http():
    payload = json.dumps({"version": "1", "script": "behavior.py"}).encode()
    with patch.object(sources, "urlopen", return_value=Response(payload)):
        document = deployment.data_document("https://example.invalid/s.json")
    with pytest.raises(ValueError, match="script"):
        load_simulation_data(document)
    with pytest.raises(ValueError, match="must use HTTPS"):
        deployment.data_document("http://example.invalid/s.json")
    redirected = Response(b"{}", url="http://example.invalid/s.json")
    with patch.object(sources, "urlopen", return_value=redirected):
        with pytest.raises(ValueError, match="redirect must use HTTPS"):
            sources.model_document("https://example.invalid/m.json")
