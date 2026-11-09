"""HTTPS model and scenario sources."""

from io import BytesIO
import json
from unittest.mock import patch

import pytest

from modsim import __version__, deployment, sources


class Response(BytesIO):
    def __init__(self, payload, url="https://example.invalid/file.json"):
        super().__init__(payload)
        self.url = url

    def geturl(self):
        return self.url


def test_remote_documents_identify_modsim():
    payload = json.dumps({"version": "1", "tick": 0.5}).encode()
    with patch.object(sources, "urlopen", return_value=Response(payload)) as remote:
        scenario = deployment.document(
            "https://example.invalid/device.sim.json", deployment.SCENARIO
        )
    assert scenario == {"version": "1", "tick": 0.5}
    request = remote.call_args.args[0]
    assert request.full_url == "https://example.invalid/device.sim.json"
    assert request.get_header("User-agent") == f"modsim/{__version__}"


def test_remote_scenarios_reject_scripts_and_plain_http():
    payload = json.dumps({"version": "1", "script": "behavior.py"}).encode()
    with patch.object(sources, "urlopen", return_value=Response(payload)):
        with pytest.raises(ValueError, match="cannot reference scripts"):
            deployment.document("https://example.invalid/s.json", deployment.SCENARIO)
    with pytest.raises(ValueError, match="must use HTTPS"):
        deployment.document("http://example.invalid/s.json", deployment.SCENARIO)
    redirected = Response(b"{}", url="http://example.invalid/s.json")
    with patch.object(sources, "urlopen", return_value=redirected):
        with pytest.raises(ValueError, match="redirect must use HTTPS"):
            sources.model_document("https://example.invalid/m.json")
