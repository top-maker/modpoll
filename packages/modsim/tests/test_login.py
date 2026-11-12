"""Sign in to ModioHub and read Workspace Thing Models (POLL-02b)."""

import hashlib
import io
import json
import os
import stat
import sys
from unittest.mock import patch
from urllib.error import HTTPError

import modpoll_wot
import pytest

from modsim import hub, login, main, sources

SERVER = "https://hub.test"
ID = "k3x9f2m7q4a8n5bd"


@pytest.fixture(autouse=True)
def isolated_login(monkeypatch, tmp_path):
    monkeypatch.setenv("MODIOHUB_URL", SERVER)
    monkeypatch.setenv("MODIOHUB_CREDENTIALS", str(tmp_path / "credentials.json"))
    monkeypatch.delenv("MODIOHUB_TOKEN", raising=False)
    return tmp_path / "credentials.json"


class Answer(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def reply(status, body):
    payload = body if isinstance(body, bytes) else json.dumps(body).encode()
    if status < 400:
        answer = Answer(payload)
        answer.status = status
        return answer
    return HTTPError("https://hub.test", status, "error", {}, io.BytesIO(payload))


def fake_hub(routes, calls):
    """Answer by URL suffix; a list is consumed in order. Records (method, url, token)."""

    def urlopen(request, timeout=None):
        calls.append(
            (
                request.get_method(),
                request.full_url,
                request.get_header("Authorization"),
            )
        )
        for suffix, answer in routes.items():
            if request.full_url.endswith(suffix):
                result = answer.pop(0) if isinstance(answer, list) else answer
                if isinstance(result, HTTPError):
                    raise result
                return result
        raise AssertionError(f"unexpected request {request.full_url}")

    return patch.object(hub, "urlopen", urlopen)


def grant():
    return reply(
        200,
        {
            "device_code": "secret",
            "user_code": "ABCD1234",
            "interval": 5,
            "expires_in": 900,
            "verification_uri": f"{SERVER}/activate/",
            "verification_uri_complete": f"{SERVER}/activate/?user_code=ABCD1234",
        },
    )


def test_login_waits_for_the_browser_and_shares_the_login_with_modpoll(isolated_login):
    calls = []
    routes = {
        "/device-authorization": [grant()],
        "/token": [
            reply(400, {"error": "authorization_pending"}),
            reply(400, {"error": "slow_down"}),
            reply(
                200,
                {"access_token": "tok", "token_type": "Bearer", "expires_in": 604800},
            ),
        ],
        "/api/v1/me": [reply(200, {"githubUser": "octo"})],
    }
    slept, out = [], io.StringIO()
    with fake_hub(routes, calls):
        session = login.login(
            SERVER, sleep=slept.append, open_browser=lambda url: False, out=out
        )
    assert slept == [5, 5, 10]
    assert (
        "ABCD1234" in out.getvalue()
        and "Open that address in a browser" in out.getvalue()
    )
    assert calls[0][:2] == (
        "POST",
        f"{SERVER}/api/v1/tool-sessions/device-authorization",
    )
    assert ("GET", f"{SERVER}/api/v1/me", "Bearer tok") in calls
    assert (session.token, session.github_user) == ("tok", "octo")
    assert modpoll_wot.load_session(SERVER).token == "tok"
    if os.name == "posix":
        assert stat.S_IMODE(isolated_login.stat().st_mode) == 0o600


@pytest.mark.parametrize(
    "error, message",
    [
        ("access_denied", "denied"),
        ("expired_token", "expired"),
        ("invalid_grant", "failed"),
    ],
)
def test_login_ends_with_a_reason(error, message):
    routes = {
        "/device-authorization": [grant()],
        "/token": [reply(400, {"error": error})],
    }
    with fake_hub(routes, []), pytest.raises(login.LoginError, match=message):
        login.login(
            SERVER,
            sleep=lambda seconds: None,
            open_browser=lambda url: True,
            out=io.StringIO(),
        )
    assert modpoll_wot.load_session(SERVER) is None


def test_commands(capsys):
    routes = {
        "/device-authorization": [grant()],
        "/token": [reply(200, {"access_token": "tok", "expires_in": 60})],
        "/api/v1/me": [reply(200, {"githubUser": "octo"})],
    }
    with (
        fake_hub(routes, []),
        patch.object(login.webbrowser, "open", return_value=True),
        patch.object(login.time, "sleep"),
    ):
        assert login.command(["login"]) == 0
    assert (
        "Signed in to https://hub.test as @octo. modpoll uses the same login."
        in capsys.readouterr().out
    )
    assert login.command(["logout"]) == 0
    assert "revoke it in Settings" in capsys.readouterr().out
    assert login.command(["logout"]) == 0
    assert "No stored login" in capsys.readouterr().out
    assert login.command(["login", "--server", "http://example.com"]) == 1
    assert login.command(["login", "--bogus"]) == 1


def test_login_and_logout_run_before_the_normal_arguments(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["modsim", "logout"])
    with pytest.raises(SystemExit) as exit_info:
        main.app()
    assert exit_info.value.code == 0


def model(
    *, status=200, sha256=None, file_url=None, versions=None, body=b'{"title": "meter"}'
):
    versions = versions or [
        {
            "version": 2,
            "sha256": sha256 or hashlib.sha256(body).hexdigest(),
            "fileUrl": file_url or f"{SERVER}/api/v1/thing-models/{ID}/versions/2/file",
        }
    ]
    return {
        f"/thing-models/{ID}": reply(status, {"versions": versions}),
        "/versions/2/file": reply(200, body),
    }


def test_a_workspace_model_is_read_with_the_login_and_checked():
    modpoll_wot.save_session(SERVER, "tok", expires_in=3600)
    calls = []
    with fake_hub(model(), calls):
        assert sources.model_document(f"modiohub:{ID}@latest") == {"title": "meter"}
    assert {token for _, _, token in calls} == {"Bearer tok"}
    with fake_hub(model(), []), pytest.raises(ValueError, match="no version 5"):
        sources.model_document(f"modiohub:{ID}@5")


def test_a_shared_model_needs_no_login_and_a_private_one_says_so():
    calls = []
    with fake_hub(model(), calls):
        sources.model_document(f"modiohub:{ID}@2")
    assert {token for _, _, token in calls} == {None}
    with (
        fake_hub(model(status=404), []),
        pytest.raises(ValueError, match="run modsim login if it is yours"),
    ):
        sources.model_document(f"modiohub:{ID}")


def test_a_download_that_does_not_match_or_leaves_the_server_is_refused():
    modpoll_wot.save_session(SERVER, "tok", expires_in=3600)
    with (
        fake_hub(model(sha256="0" * 64), []),
        pytest.raises(ValueError, match="SHA-256"),
    ):
        sources.model_document(f"modiohub:{ID}@2")
    calls = []
    with (
        fake_hub(model(file_url="https://elsewhere.test/m.json"), calls),
        pytest.raises(ValueError, match="another address"),
    ):
        sources.model_document(f"modiohub:{ID}@2")
    assert all(url.startswith(SERVER) for _, url, _ in calls)


def test_a_bad_reference_and_a_deployment_manifest_do_not_use_the_login():
    with pytest.raises(ValueError, match="modiohub:<id>@<version>"):
        sources.model_document("modiohub:nope")
