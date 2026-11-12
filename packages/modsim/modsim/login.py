"""Sign in to ModioHub with the browser authorization flow (OAuth device authorization grant, RFC 8628).

``modsim login`` asks for a code, the user confirms it in the browser, and the tool session token that comes
back is kept in the credentials file shared with modpoll (see modpoll_wot.session). ``modsim logout`` removes it.
"""

import sys
import time
import webbrowser
from typing import Any, Callable, TextIO

import modpoll_wot  # type: ignore[import-untyped]

from .hub import call_json

CLIENT_ID = "modsim"
GRANT_TYPE = "urn:ietf:params:oauth:grant-type:device_code"


class LoginError(ValueError):
    """The login did not complete; the message says why and what to do."""


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
    open_browser, out = open_browser or webbrowser.open, out or sys.stdout
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
        print("Open that address in a browser on any computer.", file=out, flush=True)
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
        session = login(server, out=out)
        who = f" as @{session.github_user}" if session.github_user else ""
        print(f"Signed in to {server}{who}. modpoll uses the same login.", file=out)
        return 0
    except (LoginError, modpoll_wot.CredentialError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
