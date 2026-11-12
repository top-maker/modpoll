"""Tool session credentials and Workspace references (POLL-02b): format, location and permissions."""

from datetime import datetime, timedelta, timezone
import json
import os
import stat

import pytest

import modpoll_wot
from modpoll_wot import CredentialError

NOW = datetime(2026, 11, 12, 8, 0, tzinfo=timezone.utc)
SERVER = "https://modiohub.com"


def environ(tmp_path, **extra):
    return {"MODIOHUB_CREDENTIALS": str(tmp_path / "credentials.json"), **extra}


def test_a_saved_login_is_found_until_it_expires(tmp_path):
    env = environ(tmp_path)
    path = modpoll_wot.save_session(SERVER, "tok", expires_in=604800, github_user="octo", environ=env, now=NOW)
    session = modpoll_wot.load_session(environ=env, now=NOW + timedelta(days=6))
    assert (session.server, session.token, session.github_user, session.source) == (SERVER, "tok", "octo", "file")
    assert session.expires_at == NOW + timedelta(days=7)
    assert modpoll_wot.load_session(environ=env, now=NOW + timedelta(days=7)) is None
    assert json.loads(path.read_text()) == {
        "version": 1,
        "servers": {SERVER: {"token": "tok", "expiresAt": "2026-11-19T08:00:00Z", "githubUser": "octo"}},
    }


@pytest.mark.skipif(os.name != "posix", reason="file modes")
def test_the_file_is_private_and_a_readable_one_is_refused(tmp_path):
    env = environ(tmp_path)
    path = modpoll_wot.save_session(SERVER, "tok", expires_in=60, environ=env, now=NOW)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    path.chmod(0o644)
    with pytest.raises(CredentialError, match="chmod 600"):
        modpoll_wot.load_session(environ=env, now=NOW)


def test_each_server_keeps_its_own_login_and_forgetting_one_keeps_the_rest(tmp_path):
    env = environ(tmp_path)
    modpoll_wot.save_session(SERVER, "prod", expires_in=60, environ=env, now=NOW)
    modpoll_wot.save_session("https://modsim.dev", "staging", expires_in=60, environ=env, now=NOW)
    assert modpoll_wot.load_session("https://modsim.dev", environ=env, now=NOW).token == "staging"
    assert modpoll_wot.forget_session(SERVER, environ=env) is True
    assert modpoll_wot.forget_session(SERVER, environ=env) is False
    assert modpoll_wot.load_session(SERVER, environ=env, now=NOW) is None
    assert modpoll_wot.load_session("https://modsim.dev", environ=env, now=NOW).token == "staging"


def test_the_environment_token_wins_and_names_no_expiry(tmp_path):
    env = environ(tmp_path, MODIOHUB_TOKEN="from-env", MODIOHUB_URL="https://modsim.dev/")
    modpoll_wot.save_session("https://modsim.dev", "stored", expires_in=60, environ=env, now=NOW)
    session = modpoll_wot.load_session(environ=env, now=NOW)
    assert (session.token, session.server, session.expires_at, session.source) == ("from-env", "https://modsim.dev", None, "environment")


def test_nothing_stored_is_not_an_error(tmp_path):
    assert modpoll_wot.load_session(environ=environ(tmp_path), now=NOW) is None
    assert modpoll_wot.forget_session(environ=environ(tmp_path)) is False


def test_a_broken_file_is_reported_and_never_overwritten(tmp_path):
    env = environ(tmp_path)
    (tmp_path / "credentials.json").write_text("not json")
    (tmp_path / "credentials.json").chmod(0o600)
    with pytest.raises(CredentialError, match="cannot be read"):
        modpoll_wot.save_session(SERVER, "tok", expires_in=60, environ=env, now=NOW)
    assert (tmp_path / "credentials.json").read_text() == "not json"


@pytest.mark.parametrize(
    "value, expected",
    [(None, SERVER), ("https://modsim.dev", "https://modsim.dev"), ("https://modsim.dev/", "https://modsim.dev"),
     ("http://127.0.0.1:8787", "http://127.0.0.1:8787"), ("http://localhost", "http://localhost")],
)
def test_server_addresses(value, expected):
    assert modpoll_wot.server_url({"MODIOHUB_URL": value} if value else {}) == expected


@pytest.mark.parametrize("value", ["ftp://x.test", "http://example.com", "https://example.com/api", "https://u:p@example.com", "modiohub.com"])
def test_server_addresses_that_would_send_a_token_astray_are_refused(value):
    with pytest.raises(CredentialError):
        modpoll_wot.server_url({"MODIOHUB_URL": value})


def test_default_locations():
    from modpoll_wot.session import credentials_path

    home = {"XDG_CONFIG_HOME": "/xdg"}
    assert str(credentials_path(home, "linux")) == "/xdg/modiohub/credentials.json"
    assert credentials_path({"APPDATA": "C:/Users/me/AppData/Roaming"}, "win32").as_posix() == "C:/Users/me/AppData/Roaming/modiohub/credentials.json"


def test_workspace_references():
    assert modpoll_wot.parse_reference("modiohub:k3x9f2m7q4a8n5bd@2") == modpoll_wot.Reference("k3x9f2m7q4a8n5bd", "2")
    assert modpoll_wot.parse_reference("modiohub:k3x9f2m7q4a8n5bd@latest").version == "latest"
    assert modpoll_wot.parse_reference("modiohub:k3x9f2m7q4a8n5bd").version == "latest"
    for bad in ("modiohub:short@1", "k3x9f2m7q4a8n5bd@1", "modiohub:k3x9f2m7q4a8n5bd@0", "modiohub:k3x9f2m7q4a8n5bd@1000", "modiohub:K3X9F2M7Q4A8N5BD@1"):
        with pytest.raises(ValueError):
            modpoll_wot.parse_reference(bad)
