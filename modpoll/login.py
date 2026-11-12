"""Sign in to ModioHub with the browser authorization flow (OAuth device authorization grant, RFC 8628).

``modpoll login`` asks for a code, the user confirms it in the browser, and the tool session token that comes
back is kept in the credentials file shared with modsim (see modpoll_wot.session). ``modpoll logout`` removes it.
"""

import os
import shutil
import subprocess
import sys
import time
import webbrowser

import modpoll_wot
import requests

from . import __version__

CLIENT_ID = "modpoll"
GRANT_TYPE = "urn:ietf:params:oauth:grant-type:device_code"
REQUEST_TIMEOUT = 15


class LoginError(ValueError):
    """The login did not complete; the message says why and what to do."""


def headers(token=None):
    return {
        "User-Agent": f"modpoll/{__version__}",
        "Accept": "application/json",
        **({"Authorization": f"Bearer {token}"} if token else {}),
    }


def _post(url, body):
    try:
        return requests.post(url, json=body, headers=headers(), timeout=REQUEST_TIMEOUT)
    except requests.RequestException as exc:
        raise LoginError(f"Could not reach {url}: {exc}") from exc


def open_in_browser(
    url, *, environ=None, platform=None, run=subprocess.run, which=shutil.which
):
    """Try to open an address in a browser; False means the user has to open it from the printed link.

    Where there is no desktop (SSH, a minimal WSL) nothing is tried, and the opener's own complaints
    never reach the terminal.
    """
    environ = os.environ if environ is None else environ
    platform = platform or sys.platform
    if environ.get("BROWSER") or platform in ("darwin", "win32"):
        return webbrowser.open(url)
    if not (environ.get("DISPLAY") or environ.get("WAYLAND_DISPLAY")) or environ.get(
        "SSH_CONNECTION"
    ):
        return False
    opener = which("xdg-open")
    if not opener:
        return False
    try:
        return (
            run(
                [opener, url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
            ).returncode
            == 0
        )
    except (OSError, subprocess.SubprocessError):
        return False


def login(server, *, sleep=None, monotonic=None, open_browser=None, out=None):
    """Run the flow against a server; returns the saved Session."""
    sleep, monotonic = sleep or time.sleep, monotonic or time.monotonic
    open_browser, out = open_browser or open_in_browser, out or sys.stdout
    start = _post(
        f"{server}/api/v1/tool-sessions/device-authorization", {"client_id": CLIENT_ID}
    )
    if not start.ok:
        raise LoginError(f"{server} refused the login ({start.status_code})")
    grant = start.json()
    print(
        f"To sign in, confirm the code {grant['user_code']} at:\n  {grant['verification_uri_complete']}",
        file=out,
        flush=True,
    )
    # A browser opens only where one can; otherwise the address and code above are all there is.
    if not open_browser(grant["verification_uri_complete"]):
        print(
            "Open the address above in a browser on any computer, then wait here.",
            file=out,
            flush=True,
        )
    interval = grant["interval"]
    deadline = monotonic() + grant["expires_in"]
    while monotonic() < deadline:
        sleep(interval)
        answer = _post(
            f"{server}/api/v1/tool-sessions/token",
            {
                "grant_type": GRANT_TYPE,
                "device_code": grant["device_code"],
                "client_id": CLIENT_ID,
            },
        )
        body = (
            answer.json()
            if answer.headers.get("Content-Type", "").startswith("application/json")
            else {}
        )
        if answer.ok:
            return _save(server, body)
        error = body.get("error")
        if error == "authorization_pending":
            continue
        if error == "slow_down":
            interval += 5
            continue
        if error == "access_denied":
            raise LoginError("The login was denied in the browser.")
        if error == "expired_token":
            break
        raise LoginError(f"The login failed ({error or answer.status_code}).")
    raise LoginError(
        "The code expired before it was confirmed; run modpoll login again."
    )


def _save(server, body):
    token = body["access_token"]
    me = requests.get(
        f"{server}/api/v1/me", headers=headers(token), timeout=REQUEST_TIMEOUT
    )
    user = me.json().get("githubUser") if me.ok else None
    modpoll_wot.save_session(
        server, token, expires_in=body["expires_in"], github_user=user
    )
    return modpoll_wot.load_session(server)


def command(arguments, *, out=None):
    """``login`` or ``logout`` with an optional ``--server``; returns the exit code."""
    out = out or sys.stdout
    name, rest = arguments[0], arguments[1:]
    try:
        if rest[:1] == ["--server"] and len(rest) == 2:
            server = modpoll_wot.server_url({"MODIOHUB_URL": rest[1]})
        elif not rest:
            server = modpoll_wot.server_url()
        else:
            raise LoginError(f"usage: modpoll {name} [--server URL]")
        if name == "logout":
            if modpoll_wot.forget_session(server):
                print(
                    f"Signed out of {server} on this computer. The token stays valid on the server until it expires; revoke it in Settings to end it now.",
                    file=out,
                )
            else:
                print(f"No stored login for {server}.", file=out)
            return 0
        try:
            session = login(server, out=out)
        except KeyboardInterrupt:
            print("\nLogin cancelled.", file=sys.stderr)
            return 130
        who = f" as @{session.github_user}" if session.github_user else ""
        print(f"Signed in to {server}{who}. modsim uses the same login.", file=out)
        return 0
    except (LoginError, modpoll_wot.CredentialError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
