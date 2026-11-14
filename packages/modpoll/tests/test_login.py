"""Sign in, Workspace Thing Models and report upload (POLL-02b)."""

import hashlib
import io
import json
import os
import stat
import sys

import modpoll_wot
import pytest

from modpoll import login, main, utils, verification

from .test_verification import (  # noqa: F401  (the fixture clears the process-wide stop event)
    FakeClient,
    fresh_stop_event,
    run_app,
    three_group_model,
)

SERVER = "https://hub.test"
ID = "k3x9f2m7q4a8n5bd"
PRODUCT = "acme/meter"


@pytest.fixture(autouse=True)
def isolated_login(monkeypatch, tmp_path):
    monkeypatch.setenv("MODIOHUB_URL", SERVER)
    monkeypatch.setenv("MODIOHUB_CREDENTIALS", str(tmp_path / "credentials.json"))
    monkeypatch.delenv("MODIOHUB_TOKEN", raising=False)
    return tmp_path / "credentials.json"


class Reply:
    def __init__(
        self, status=200, body=None, content=b"", content_type="application/json"
    ):
        self.status_code, self._body, self.content = status, body, content
        self.headers = {"Content-Type": content_type}
        self.ok = status < 400

    def json(self):
        return self._body


def device_flow(monkeypatch, answers):
    """Fake the three requests of a login; `answers` are the token endpoint's replies in order."""
    calls = []

    def post(url, json=None, headers=None, timeout=None):
        calls.append(("POST", url, json))
        if url.endswith("/device-authorization"):
            return Reply(
                body={
                    "device_code": "secret",
                    "user_code": "ABCD1234",
                    "interval": 5,
                    "expires_in": 900,
                    "verification_uri": f"{SERVER}/activate/",
                    "verification_uri_complete": f"{SERVER}/activate/?user_code=ABCD1234",
                }
            )
        return answers.pop(0)

    def get(url, headers=None, timeout=None):
        calls.append(("GET", url, headers.get("Authorization")))
        return Reply(body={"githubUser": "octo"})

    monkeypatch.setattr(login.requests, "post", post)
    monkeypatch.setattr(login.requests, "get", get)
    return calls


def test_login_waits_for_the_browser_and_keeps_one_login_for_both_tools(
    monkeypatch, isolated_login
):
    answers = [
        Reply(400, {"error": "authorization_pending"}),
        Reply(400, {"error": "slow_down"}),
        Reply(
            200, {"access_token": "tok", "token_type": "Bearer", "expires_in": 604800}
        ),
    ]
    calls = device_flow(monkeypatch, answers)
    slept, out = [], io.StringIO()
    session = login.login(
        SERVER, sleep=slept.append, open_browser=lambda url: False, out=out
    )
    assert slept == [5, 5, 10]  # slow_down adds five seconds
    assert (
        "ABCD1234" in out.getvalue()
        and f"{SERVER}/activate/?user_code=ABCD1234" in out.getvalue()
    )
    assert "Open the address above in a browser" in out.getvalue()
    assert calls[0][2] == {"client_id": "modpoll"}
    assert ("GET", f"{SERVER}/api/v1/me", "Bearer tok") in calls
    assert (session.token, session.github_user, session.source) == (
        "tok",
        "octo",
        "file",
    )
    # modsim reads the same file through modpoll-wot.
    assert modpoll_wot.load_session(SERVER).token == "tok"
    if os.name == "posix":
        assert stat.S_IMODE(isolated_login.stat().st_mode) == 0o600


@pytest.mark.parametrize(
    "reply, message",
    [
        (Reply(400, {"error": "access_denied"}), "denied"),
        (Reply(400, {"error": "expired_token"}), "expired"),
        (Reply(500, None, content_type="text/plain"), "failed"),
    ],
)
def test_login_ends_with_a_reason(monkeypatch, reply, message):
    device_flow(monkeypatch, [reply])
    with pytest.raises(login.LoginError, match=message):
        login.login(
            SERVER,
            sleep=lambda seconds: None,
            open_browser=lambda url: True,
            out=io.StringIO(),
        )
    assert modpoll_wot.load_session(SERVER) is None


def test_the_code_expires_when_nobody_confirms(monkeypatch):
    device_flow(monkeypatch, [Reply(400, {"error": "authorization_pending"})] * 100)
    clock = iter(range(0, 10_000, 400))
    with pytest.raises(login.LoginError, match="expired"):
        login.login(
            SERVER,
            sleep=lambda seconds: None,
            monotonic=lambda: next(clock),
            open_browser=lambda url: True,
            out=io.StringIO(),
        )


def test_login_and_logout_commands(monkeypatch, capsys):
    device_flow(monkeypatch, [Reply(200, {"access_token": "tok", "expires_in": 60})])
    monkeypatch.setattr(login, "open_in_browser", lambda url: True)
    monkeypatch.setattr(login.time, "sleep", lambda seconds: None)
    assert login.command(["login"]) == 0
    assert (
        "Signed in to https://hub.test as @octo. modsim uses the same login."
        in capsys.readouterr().out
    )
    assert login.command(["logout"]) == 0
    assert "revoke it in Settings" in capsys.readouterr().out
    assert login.command(["logout"]) == 0
    assert "No stored login" in capsys.readouterr().out
    assert login.command(["login", "--server", "http://example.com"]) == 1
    assert login.command(["login", "--bogus"]) == 1


def test_login_and_logout_run_before_the_normal_arguments(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["modpoll", "logout"])
    with pytest.raises(SystemExit) as exit_info:
        main.app()
    assert exit_info.value.code == 0


def workspace(
    monkeypatch, *, payload, versions=None, status=200, file_url=None, sha256=None
):
    versions = versions or [
        {
            "version": 2,
            "sha256": sha256 or hashlib.sha256(payload).hexdigest(),
            "fileUrl": file_url or f"{SERVER}/api/v1/thing-models/{ID}/versions/2/file",
        }
    ]
    seen = []

    def get(url, headers=None, timeout=None):
        seen.append((url, headers.get("Authorization")))
        if url.endswith(f"/thing-models/{ID}"):
            return Reply(status, {"productId": PRODUCT, "versions": versions})
        return Reply(200, content=payload)

    monkeypatch.setattr(verification.requests, "get", get)
    return seen


def test_a_workspace_model_is_fetched_with_the_login_and_checked(monkeypatch):
    payload = json.dumps(three_group_model()).encode()
    modpoll_wot.save_session(SERVER, "tok", expires_in=3600, github_user="octo")
    seen = workspace(monkeypatch, payload=payload)
    assert verification.fetch_workspace_model(f"modiohub:{ID}@latest", timeout=3) == (
        payload,
        {"product": PRODUCT, "ref": f"{ID}@2"},
    )
    assert {token for _, token in seen} == {"Bearer tok"}
    with pytest.raises(ValueError, match="no version 5"):
        verification.fetch_workspace_model(f"modiohub:{ID}@5", timeout=3)


def test_a_shared_model_needs_no_login_and_a_private_one_says_so(monkeypatch):
    payload = b'{"title": "x"}'
    seen = workspace(monkeypatch, payload=payload)
    verification.fetch_workspace_model(f"modiohub:{ID}@2", timeout=3)
    assert {token for _, token in seen} == {None}
    workspace(monkeypatch, payload=payload, status=404)
    with pytest.raises(ValueError, match="run modpoll login if it is yours"):
        verification.fetch_workspace_model(f"modiohub:{ID}", timeout=3)


def test_a_download_that_does_not_match_or_leaves_the_server_is_refused(monkeypatch):
    modpoll_wot.save_session(SERVER, "tok", expires_in=3600)
    workspace(monkeypatch, payload=b"{}", sha256="0" * 64)
    with pytest.raises(ValueError, match="SHA-256"):
        verification.fetch_workspace_model(f"modiohub:{ID}@2", timeout=3)
    seen = workspace(
        monkeypatch, payload=b"{}", file_url="https://elsewhere.test/model.json"
    )
    with pytest.raises(ValueError, match="another address"):
        verification.fetch_workspace_model(f"modiohub:{ID}@2", timeout=3)
    assert all(url.startswith(SERVER) for url, _ in seen)


def test_full_read_of_a_workspace_model_names_the_workspace_as_its_source(
    monkeypatch, tmp_path
):
    payload = json.dumps(three_group_model()).encode()
    workspace(monkeypatch, payload=payload)
    report_path = tmp_path / "report.json"
    with pytest.raises(SystemExit):
        run_app(
            monkeypatch,
            [
                "--config",
                f"modiohub:{ID}@2",
                "--tcp",
                "x",
                "--report",
                str(report_path),
            ],
            FakeClient(),
        )
    report = json.loads(report_path.read_text())
    assert report["product"] == PRODUCT
    assert (
        report["model"]["source"] == "workspace" and report["model"]["ref"] == f"{ID}@2"
    )
    modpoll_wot.validate_report(report, model=payload)


def test_upload_shows_the_report_and_sends_it_with_the_login(
    monkeypatch, tmp_path, capsys
):
    payload = json.dumps(three_group_model()).encode()
    path = tmp_path / "meter.tm.json"
    path.write_bytes(payload)
    monkeypatch.chdir(tmp_path)
    modpoll_wot.save_session(SERVER, "tok", expires_in=3600)
    sent = {}

    def post(url, json=None, headers=None, timeout=None):
        sent.update(url=url, body=json, headers=headers)
        return Reply(201, {"id": "p7n2d9x4k8m3q5ra"})

    monkeypatch.setattr(verification.requests, "post", post)
    run_app(
        monkeypatch,
        ["-f", str(path), "--tcp", "x", "--report", "--upload", "--yes"],
        FakeClient(False, False),
    )
    out = capsys.readouterr().out
    assert "Report to upload:" in out and "Uploaded. Thank you" in out
    assert (
        sent["url"] == f"{SERVER}/api/v1/reports" and sent["body"]["reportVersion"] == 5
    )
    assert "product" not in sent["body"]
    assert (
        sent["headers"]["Authorization"] == "Bearer tok"
        and sent["headers"]["Idempotency-Key"]
    )


def test_upload_asks_first_and_needs_a_login(monkeypatch, tmp_path, capsys):
    # The scripted answers also reach the save-location prompt; keep that report out of the repository.
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "meter.tm.json"
    path.write_text(json.dumps(three_group_model()))
    posted = []
    monkeypatch.setattr(
        verification.requests,
        "post",
        lambda *args, **kwargs: posted.append(args)
        or Reply(201, {"id": "p7n2d9x4k8m3q5ra"}),
    )
    arguments = ["-f", str(path), "--tcp", "x", "--report", "--upload"]
    # Not a terminal and no --yes: nothing is sent.
    with pytest.raises(SystemExit) as exit_info:
        run_app(monkeypatch, arguments, FakeClient(False, False))
    assert exit_info.value.code == 1 and not posted
    # A terminal where the user declines.
    utils._thread_event.clear()
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt: "n")
    with pytest.raises(SystemExit):
        run_app(monkeypatch, arguments, FakeClient(False, False))
    assert "Not uploaded." in capsys.readouterr().out and not posted
    # Agreeing without a login starts the sign-in flow; when it fails, nothing is sent.
    utils._thread_event.clear()
    monkeypatch.setattr("builtins.input", lambda prompt: "y")
    monkeypatch.setattr(
        login,
        "login",
        lambda *a, **k: (_ for _ in ()).throw(login.LoginError("no browser here")),
    )
    with pytest.raises(SystemExit):
        run_app(monkeypatch, arguments, FakeClient(False, False))
    assert not posted


def test_a_refused_upload_reports_why(monkeypatch):
    modpoll_wot.save_session(SERVER, "tok", expires_in=3600)
    monkeypatch.setattr(
        verification.requests,
        "post",
        lambda *a, **k: Reply(422, {"detail": "No product x/y in the catalog."}),
    )
    with pytest.raises(ValueError, match="No product x/y"):
        verification.upload_report({}, timeout=3)
    monkeypatch.setattr(verification.requests, "post", lambda *a, **k: Reply(401, {}))
    with pytest.raises(ValueError, match="modpoll login"):
        verification.upload_report({}, timeout=3)


def test_upload_signs_in_inline_when_there_is_no_session(monkeypatch, tmp_path, capsys):
    """An interactive upload without a login starts the browser flow and continues with the session."""
    path = tmp_path / "meter.tm.json"
    path.write_text(json.dumps(three_group_model()))
    monkeypatch.chdir(tmp_path)
    posted = []
    monkeypatch.setattr(
        verification.requests,
        "post",
        lambda *args, **kwargs: posted.append(args)
        or Reply(201, {"id": "p7n2d9x4k8m3q5ra"}),
    )
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt: "y")

    def fake_login(server, **kwargs):
        modpoll_wot.save_session(server, "tok", expires_in=3600)
        return modpoll_wot.load_session(server)

    monkeypatch.setattr(login, "login", fake_login)
    run_app(
        monkeypatch,
        ["-f", str(path), "--tcp", "x", "--report", "--upload"],
        FakeClient(False, False),
    )
    assert posted
    assert "signed in to" in capsys.readouterr().out


class Finished:
    def __init__(self, returncode):
        self.returncode = returncode


@pytest.mark.parametrize(
    "environ, platform, expected_calls",
    [
        ({"DISPLAY": ":0"}, "linux", 1),
        ({"WAYLAND_DISPLAY": "wayland-0"}, "linux", 1),
        ({}, "linux", 0),  # no desktop: SSH or a minimal WSL
        ({"DISPLAY": ":0", "SSH_CONNECTION": "1 2 3 4"}, "linux", 0),
    ],
)
def test_a_browser_is_tried_only_where_there_is_a_desktop(
    environ, platform, expected_calls
):
    calls = []
    opened = login.open_in_browser(
        "https://hub.test/activate/?user_code=X",
        environ=environ,
        platform=platform,
        run=lambda command, **options: calls.append((command, options)) or Finished(0),
        which=lambda name: "/usr/bin/xdg-open",
    )
    assert len(calls) == expected_calls and opened is bool(expected_calls)
    if calls:
        # The opener's complaints stay out of the terminal.
        assert (
            calls[0][1]["stdout"] == login.subprocess.DEVNULL
            and calls[0][1]["stderr"] == login.subprocess.DEVNULL
        )


def test_an_opener_that_finds_no_browser_or_is_missing_is_a_failure_not_noise():
    environ = {"DISPLAY": ":0"}
    assert (
        login.open_in_browser(
            "https://x.test",
            environ=environ,
            platform="linux",
            run=lambda *a, **k: Finished(3),
            which=lambda name: "/usr/bin/xdg-open",
        )
        is False
    )
    assert (
        login.open_in_browser(
            "https://x.test", environ=environ, platform="linux", which=lambda name: None
        )
        is False
    )

    def broken(*args, **kwargs):
        raise OSError("gone")

    assert (
        login.open_in_browser(
            "https://x.test",
            environ=environ,
            platform="linux",
            run=broken,
            which=lambda name: "/usr/bin/xdg-open",
        )
        is False
    )


def test_the_browser_variable_and_other_platforms_use_the_standard_opener(monkeypatch):
    seen = []
    monkeypatch.setattr(login.webbrowser, "open", lambda url: seen.append(url) or True)
    assert (
        login.open_in_browser(
            "https://a.test", environ={"BROWSER": "wslview"}, platform="linux"
        )
        is True
    )
    assert (
        login.open_in_browser("https://b.test", environ={}, platform="darwin") is True
    )
    assert seen == ["https://a.test", "https://b.test"]


def test_ctrl_c_while_waiting_is_a_one_line_cancel(monkeypatch, capsys):
    def interrupted(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(login, "login", interrupted)
    assert login.command(["login"]) == 130
    assert "Login cancelled." in capsys.readouterr().err
