"""Tool session credentials and workspace references, shared by modpoll and modsim.

This module only defines where a tool session token is kept and how a Workspace Thing Model is named. It
makes no request: signing in (the OAuth device authorization flow against ModioHub) belongs to each tool,
so every tool that reads this file works with a login made by any other.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
from urllib.parse import urlsplit

DEFAULT_SERVER = "https://modiohub.com"
TOKEN_VARIABLE = "MODIOHUB_TOKEN"
SERVER_VARIABLE = "MODIOHUB_URL"
FILE_VARIABLE = "MODIOHUB_CREDENTIALS"
REFERENCE_PREFIX = "modiohub:"
FILE_VERSION = 1
_REFERENCE = re.compile(r"^modiohub:([a-z0-9]{16})(?:@([1-9][0-9]{0,2}|latest))?$")
_LOCAL = {"localhost", "127.0.0.1", "::1"}


class CredentialError(ValueError):
    """The credentials file or a server address cannot be used."""


@dataclass(frozen=True)
class Session:
    server: str
    token: str
    github_user: str | None
    expires_at: datetime | None
    source: str  # "environment" or "file"


@dataclass(frozen=True)
class Reference:
    id: str
    version: str  # a number as text, or "latest"


def parse_reference(text):
    """Parse ``modiohub:<id>[@<version>]``; the version is a number or ``latest`` (the default)."""
    match = _REFERENCE.match(text)
    if not match:
        raise ValueError(
            "a Workspace Thing Model is named modiohub:<id>@<version>, "
            "where the version is a number or latest"
        )
    return Reference(match.group(1), match.group(2) or "latest")


def server_url(environ=None):
    """The ModioHub origin: ``MODIOHUB_URL`` or the default; https, except for a local server."""
    environ = os.environ if environ is None else environ
    text = environ.get(SERVER_VARIABLE) or DEFAULT_SERVER
    parts = urlsplit(text)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise CredentialError(f"{SERVER_VARIABLE} must be an http(s) address")
    if parts.scheme == "http" and parts.hostname not in _LOCAL:
        raise CredentialError(f"{SERVER_VARIABLE} must use https unless the server is local")
    if parts.path not in ("", "/") or parts.query or parts.fragment or parts.username:
        raise CredentialError(f"{SERVER_VARIABLE} must be an origin such as {DEFAULT_SERVER}")
    return f"{parts.scheme}://{parts.netloc}"


def credentials_path(environ=None, platform=None):
    """``MODIOHUB_CREDENTIALS``, else ``modiohub/credentials.json`` in the user's configuration directory."""
    environ = os.environ if environ is None else environ
    if environ.get(FILE_VARIABLE):
        return Path(environ[FILE_VARIABLE])
    if (platform or sys.platform) == "win32":
        base = Path(environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    else:
        base = Path(environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "modiohub" / "credentials.json"


def _now(now):
    return now or datetime.now(timezone.utc)


def _read(path):
    try:
        mode = path.stat().st_mode
    except FileNotFoundError:
        return {"version": FILE_VERSION, "servers": {}}
    if os.name == "posix" and mode & (stat.S_IRWXG | stat.S_IRWXO):
        raise CredentialError(f"{path} must only be readable by you; run chmod 600 {path}")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CredentialError(f"{path} cannot be read: {exc}") from exc
    if (
        not isinstance(document, dict)
        or document.get("version") != FILE_VERSION
        or not isinstance(document.get("servers"), dict)
    ):
        raise CredentialError(f"{path} is not a version {FILE_VERSION} credentials file")
    return document


def _expiry(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def load_session(server=None, *, environ=None, now=None):
    """The session for a server, or None: ``MODIOHUB_TOKEN`` wins, then the credentials file.

    A token from the environment has no known expiry; an expired token in the file is ignored.
    """
    environ = os.environ if environ is None else environ
    server = server or server_url(environ)
    if environ.get(TOKEN_VARIABLE):
        return Session(server, environ[TOKEN_VARIABLE], None, None, "environment")
    entry = _read(credentials_path(environ)).get("servers", {}).get(server)
    if not isinstance(entry, dict) or not isinstance(entry.get("token"), str):
        return None
    try:
        expires_at = _expiry(entry["expiresAt"])
    except (KeyError, TypeError, ValueError) as exc:
        raise CredentialError(f"the stored login for {server} has no valid expiry") from exc
    if expires_at <= _now(now):
        return None
    return Session(server, entry["token"], entry.get("githubUser"), expires_at, "file")


def _write(path, document):
    path.parent.mkdir(parents=True, exist_ok=True)
    if os.name == "posix":
        path.parent.chmod(0o700)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            json.dump(document, output, indent=2)
            output.write("\n")
        if os.name == "posix":
            os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def save_session(server, token, *, expires_in, github_user=None, environ=None, now=None):
    """Keep a token for a server in a file only the user can read; other servers' logins stay."""
    path = credentials_path(environ)
    document = _read(path)
    document["servers"][server] = {
        "token": token,
        "expiresAt": (_now(now) + timedelta(seconds=expires_in)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        **({"githubUser": github_user} if github_user else {}),
    }
    _write(path, document)
    return path


def forget_session(server=None, *, environ=None):
    """Remove the stored login for a server; returns whether there was one."""
    environ = os.environ if environ is None else environ
    server = server or server_url(environ)
    path = credentials_path(environ)
    document = _read(path)
    if document["servers"].pop(server, None) is None:
        return False
    _write(path, document)
    return True


def active_server(environ=None, *, now=None):
    """The server a tool should talk to when the user did not name one.

    ``MODIOHUB_URL`` wins. Without it, the default server stands when it has a
    live session; otherwise the only stored server with a live session wins, so
    a login made against one ModioHub (for example staging) keeps working in
    later commands. With no live session, or with live sessions on several
    servers, the default is returned and the caller starts the sign-in flow.
    """
    environ = os.environ if environ is None else environ
    if environ.get(SERVER_VARIABLE):
        return server_url(environ)
    default = server_url(environ)
    if load_session(default, environ=environ, now=now) is not None:
        return default
    origins = [
        origin
        for origin in _read(credentials_path(environ)).get("servers", {})
        if load_session(origin, environ=environ, now=now) is not None
    ]
    if len(origins) == 1:
        return origins[0]
    return default
