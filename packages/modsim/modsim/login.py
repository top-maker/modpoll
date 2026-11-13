"""Sign in to ModioHub with the browser authorization flow (OAuth device authorization grant, RFC 8628).

``modsim login`` asks for a code, the user confirms it in the browser, and the tool session token that comes
back is kept in the credentials file shared with modpoll (see modpoll_wot.session). ``modsim logout`` removes it.
"""

import os
import shutil
import subprocess
import sys
import time
import webbrowser
from typing import Any, Callable, Mapping, TextIO

import modpoll_wot  # type: ignore[import-untyped]

from .hub import call_json

CLIENT_ID = "modsim"
GRANT_TYPE = "urn:ietf:params:oauth:grant-type:device_code"


class LoginError(ValueError):
    """The login did not complete; the message says why and what to do."""


def open_in_browser(
    url: str,
    *,
    environ: Mapping[str, str] | None = None,
    platform: str | None = None,
    run: Callable[..., Any] = subprocess.run,
    which: Callable[[str], str | None] = shutil.which,
) -> bool:
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
        return bool(
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


def login(
    server: str,
    *,
    sleep: Callable[[float], Any] | None = None,
    monotonic: Callable[[], float] | None = None,
    open_browser: Callable[[str], bool] | None = None,
    out: TextIO | None = None,
) -> Any:
    """Run the flow against a server; returns the saved Session."""
    sleep, monotonic = sleep or time.sleep, monotonic or time.monotonic
    open_browser, out = open_browser or open_in_browser, out or sys.stdout
    status, grant = call_json(
        f"{server}/api/v1/tool-sessions/device-authorization",
        method="POST",
        body={"client_id": CLIENT_ID},
    )
    if status != 200:
        raise LoginError(f"{server} refused the login ({status})")
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
        status, body = call_json(
            f"{server}/api/v1/tool-sessions/token",
            method="POST",
            body={
                "grant_type": GRANT_TYPE,
                "device_code": grant["device_code"],
                "client_id": CLIENT_ID,
            },
        )
        if status == 200:
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
        raise LoginError(f"The login failed ({error or status}).")
    raise LoginError(
        "The code expired before it was confirmed; run modsim login again."
    )


def _save(server: str, body: dict) -> Any:
    token = body["access_token"]
    status, me = call_json(f"{server}/api/v1/me", token=token)
    modpoll_wot.save_session(
        server,
        token,
        expires_in=body["expires_in"],
        github_user=me.get("githubUser") if status == 200 else None,
    )
    return modpoll_wot.load_session(server)


def command(arguments: list[str], *, out: TextIO | None = None) -> int:
    """``login`` or ``logout`` with an optional ``--server``; returns the exit code."""
    out = out or sys.stdout
    name, rest = arguments[0], arguments[1:]
    try:
        if rest[:1] == ["--server"] and len(rest) == 2:
            server = modpoll_wot.server_url({"MODIOHUB_URL": rest[1]})
        elif not rest:
            server = modpoll_wot.server_url()
        else:
            raise LoginError(f"usage: modsim {name} [--server URL]")
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
        print(f"Signed in to {server}{who}. modpoll uses the same login.", file=out)
        return 0
    except (LoginError, modpoll_wot.CredentialError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
