# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-290: serve the shell, the read-only API and the snapshot files on 127.0.0.1."""

import http.client
import mimetypes
import secrets
import socket
import socketserver
import time
from collections.abc import Callable
from enum import StrEnum
from functools import partial
from http import HTTPStatus
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import TypeVar
from urllib.parse import parse_qs, urlsplit

from .api import ApiPath, Route, UiAsset, state_json
from .workspace import Workspace

_UI = Path(__file__).parent / "ui"
_LOOPBACK = "127.0.0.1"
_PROBE_SECONDS = 2
_Member = TypeVar("_Member", bound=StrEnum)
# The shell loads only its own files and asks only its own server.
_SHELL_CSP = (
    "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "connect-src 'self'; frame-src 'self'; form-action 'none'; frame-ancestors 'none'; "
    "base-uri 'none'"
)
# The Explorer pages bring inline scripts and styles; still no other origin may load.
_FILES_CSP = (
    "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
    "img-src 'self' data:; frame-ancestors 'self'; base-uri 'none'"
)


def _cookie_name(port: int) -> str:
    # Cookies ignore the port: each server needs its own cookie name.
    return f"archkeel_studio_{port}"


class _Idle(Exception):
    """No request arrived within the idle time."""


def _decode(kind: type[_Member], value: str) -> _Member | None:
    """The member for a URL segment, or None; `in` on an enum needs Python 3.12."""
    try:
        return kind(value)
    except ValueError:
        return None


class Studio(ThreadingHTTPServer):
    """One workspace and one token; the server itself writes no file."""

    daemon_threads = True

    def __init__(self, workspace: Workspace, idle_seconds: float = 0.0) -> None:
        self.workspace = workspace
        self.token = secrets.token_urlsafe(32)
        self.idle_seconds = idle_seconds
        self.last_request = time.monotonic()
        super().__init__((_LOOPBACK, 0), partial(_Handler, self))
        self.port: int = self.socket.getsockname()[1]
        self.host = f"{_LOOPBACK}:{self.port}"
        self.cookie = _cookie_name(self.port)
        self.url = f"http://{self.host}/?token={self.token}"

    def service_actions(self) -> None:
        """Called by `serve_forever` after each poll: end the loop when no request came."""
        if self.idle_seconds > 0 and time.monotonic() - self.last_request > self.idle_seconds:
            raise _Idle


class _Handler(BaseHTTPRequestHandler):
    def __init__(
        self,
        studio: Studio,
        request: socket.socket,
        client_address: tuple[str, int],
        server: socketserver.BaseServer,
    ) -> None:
        self.studio = studio
        super().__init__(request, client_address, server)

    def log_request(self, code: int | str = "-", size: int | str = "-") -> None:
        # Only a refused or failed request is worth a line on the terminal.
        if isinstance(code, int) and code >= HTTPStatus.BAD_REQUEST:
            super().log_request(code, size)

    def _send(
        self,
        status: HTTPStatus,
        body: bytes = b"",
        content_type: str = "text/plain; charset=utf-8",
        headers: tuple[tuple[str, str], ...] = (),
        csp: str = _SHELL_CSP,
    ) -> None:
        self.studio.last_request = time.monotonic()
        self.send_response(status)
        for name, value in (
            ("Content-Type", content_type),
            ("Content-Length", str(len(body))),
            ("Content-Security-Policy", csp),
            ("Cache-Control", "no-store"),
            ("X-Content-Type-Options", "nosniff"),
            *headers,
        ):
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def _holds_token(self) -> bool:
        try:
            morsel = SimpleCookie(self.headers.get("Cookie", "")).get(self.studio.cookie)
        except CookieError:
            return False
        return morsel is not None and secrets.compare_digest(
            morsel.value.encode(), self.studio.token.encode()
        )

    def _refused(self, route: Route | None, query: str) -> bool:
        """Send 403 for another Host (DNS rebinding) or a missing token; the start URL logs in."""
        if self.headers.get("Host") != self.studio.host:
            self._send(HTTPStatus.FORBIDDEN, b"forbidden\n")
            return True
        token = parse_qs(query).get("token", [""])[0]
        if route is Route.SHELL and token:
            if not secrets.compare_digest(token.encode(), self.studio.token.encode()):
                self._send(HTTPStatus.FORBIDDEN, b"forbidden\n")
                return True
            cookie = f"{self.studio.cookie}={self.studio.token}; HttpOnly; SameSite=Strict; Path=/"
            self._send(HTTPStatus.SEE_OTHER, headers=(("Set-Cookie", cookie), ("Location", "/")))
            return True
        if not self._holds_token():
            self._send(
                HTTPStatus.FORBIDDEN, b"forbidden: open the URL that archkeel studio printed\n"
            )
            return True
        return False

    def do_GET(self) -> None:
        url = urlsplit(self.path)
        head, _, name = url.path[1:].partition("/")
        route = _decode(Route, head)
        if self._refused(route, url.query):
            return
        if route is Route.SHELL and not name:
            self._asset(UiAsset.INDEX)
        elif route is Route.API and _decode(ApiPath, name) is ApiPath.STATE:
            self._send(HTTPStatus.OK, state_json(self.studio.workspace.state()), "application/json")
        elif route is Route.UI and (asset := _decode(UiAsset, name)) is not None:
            self._asset(asset)
        elif route is Route.FILES and (target := self.studio.workspace.file(name)) is not None:
            kind = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            self._send(HTTPStatus.OK, target.read_bytes(), kind, csp=_FILES_CSP)
        else:
            self._send(HTTPStatus.NOT_FOUND, b"not found\n")

    def _asset(self, asset: UiAsset) -> None:
        kind = mimetypes.guess_type(asset.value)[0] or "application/octet-stream"
        self._send(HTTPStatus.OK, (_UI / asset.value).read_bytes(), f"{kind}; charset=utf-8")

    def _read_only(self) -> None:
        self._send(
            HTTPStatus.METHOD_NOT_ALLOWED,
            b"the Studio API is read-only\n",
            headers=(("Allow", "GET"),),
        )

    do_POST = do_PUT = do_DELETE = do_PATCH = _read_only


def is_studio(url: str) -> bool:
    """True when a Studio answers its start URL with the login redirect; a live pid is no proof."""
    try:
        start = urlsplit(url)
        port = start.port
    except ValueError:
        return False
    if port is None:
        return False
    connection = http.client.HTTPConnection(_LOOPBACK, port, timeout=_PROBE_SECONDS)
    try:
        connection.request("GET", f"{start.path}?{start.query}")
        response = connection.getresponse()
        cookie = response.getheader("Set-Cookie", "")
    except (OSError, http.client.HTTPException):
        return False
    finally:
        connection.close()
    return response.status == HTTPStatus.SEE_OTHER and cookie.startswith(f"{_cookie_name(port)}=")


def run_studio(
    workspace: Workspace, *, ready: Callable[[str], object], idle_seconds: float = 0.0
) -> int:
    """Make the snapshot and serve until Ctrl-C or `idle_seconds` without a request (0 = never).

    `ready` gets the start URL with the token.
    """
    server = Studio(workspace, idle_seconds)
    workspace.start()
    try:
        # The caller has written its state file before the URL appears: a reader can stop us.
        ready(server.url)
        print(f"ArchKeel Studio: {server.url}\nPress Ctrl-C to stop.", flush=True)
        server.serve_forever()
    except (KeyboardInterrupt, _Idle):
        print("ArchKeel Studio: stopped.")
    finally:
        server.server_close()
        workspace.close()
    return 0
