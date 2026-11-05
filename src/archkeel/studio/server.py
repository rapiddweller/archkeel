# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-290: serve the shell, the read-only API and the snapshot files on 127.0.0.1."""

import http.client
import json
import mimetypes
import secrets
import socket
import socketserver
import time
from collections.abc import Callable
from functools import partial
from http import HTTPStatus
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .agent import Agent, Reply
from .answer import Snapshot
from .api import (
    AgentKind,
    ApiPath,
    ChatAnswer,
    ChatError,
    ChatFailure,
    ChatMode,
    ChatRequest,
    ExploreState,
    MediaType,
    Route,
    StoryDraft,
    UiAsset,
    chat_json,
    draft_json,
    failure_json,
    graph_json,
    member,
    parse_chat_request,
    parse_story_candidate,
    state_json,
    stories_json,
    story_json,
)
from .stories import provenance
from .workspace import Workspace

_UI = Path(__file__).parent / "ui"
_LOOPBACK = "127.0.0.1"
_PROBE_SECONDS = 2
_BODY_LIMIT = 16 * 1024
_SOCKET_SECONDS = 30
# A request header that a page of another origin cannot send without a CORS preflight.
_CHAT_HEADER = "X-Archkeel-Studio"
_STATUS = {
    ChatError.INVALID_REQUEST: HTTPStatus.BAD_REQUEST,
    ChatError.UNSUPPORTED_MEDIA_TYPE: HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
    ChatError.LENGTH_REQUIRED: HTTPStatus.LENGTH_REQUIRED,
    ChatError.BODY_TOO_LARGE: HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
    ChatError.SNAPSHOT_NOT_READY: HTTPStatus.SERVICE_UNAVAILABLE,
    ChatError.BUSY: HTTPStatus.CONFLICT,
    ChatError.AGENT_NOT_INSTALLED: HTTPStatus.SERVICE_UNAVAILABLE,
    ChatError.AGENT_FAILED: HTTPStatus.BAD_GATEWAY,
    ChatError.AGENT_TIMEOUT: HTTPStatus.GATEWAY_TIMEOUT,
    ChatError.OUTPUT_TOO_LARGE: HTTPStatus.BAD_GATEWAY,
    ChatError.REPOSITORY_CHANGED: HTTPStatus.BAD_GATEWAY,
    ChatError.INVALID_ANSWER: HTTPStatus.BAD_GATEWAY,
}
# The shell loads only its own files and asks only its own server.
_SHELL_CSP = (
    "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "connect-src 'self'; frame-src 'self'; form-action 'none'; frame-ancestors 'none'; "
    "base-uri 'none'"
)
# The Explorer pages bring inline scripts and styles; still no other origin may load. The sandbox
# gives the page an opaque origin (Origin: null), so a script in it cannot reach the parent page,
# the cookie or the chat route (the AD-290 hard gate, server side).
_FILES_CSP = (
    "sandbox allow-scripts; default-src 'none'; script-src 'unsafe-inline'; "
    "style-src 'unsafe-inline'; img-src 'self' data:; frame-ancestors 'self'; base-uri 'none'; "
    "form-action 'none'"
)


def _cookie_name(port: int) -> str:
    # Cookies ignore the port: each server needs its own cookie name.
    return f"archkeel_studio_{port}"


class _Idle(Exception):
    """No request arrived within the idle time."""


def _route(path: str) -> tuple[Route | None, str, ApiPath | None]:
    """The route, the rest of the path and, below `/api/`, its resource; None if unknown."""
    head, _, name = path[1:].partition("/")
    route = member(Route, head)
    return route, name, member(ApiPath, name) if route is Route.API else None


class Studio(ThreadingHTTPServer):
    """One workspace, one agent and one token; the server itself writes no file."""

    daemon_threads = True

    def __init__(
        self,
        workspace: Workspace,
        idle_seconds: float = 0.0,
        agent: AgentKind = AgentKind.CLAUDE,
    ) -> None:
        self.workspace = workspace
        self.agent = Agent(workspace.root, agent)
        self.token = secrets.token_urlsafe(32)
        self.idle_seconds = idle_seconds
        self.serving: Callable[[], object] | None = None
        self.last_request = time.monotonic()
        super().__init__((_LOOPBACK, 0), partial(_Handler, self))
        self.port: int = self.socket.getsockname()[1]
        self.host = f"{_LOOPBACK}:{self.port}"
        self.cookie = _cookie_name(self.port)
        self.url = f"http://{self.host}/?token={self.token}"

    def service_actions(self) -> None:
        """Called by `serve_forever` after its first poll and on each idle check."""
        if self.serving is not None:
            serving, self.serving = self.serving, None
            serving()
        quiet = time.monotonic() - self.last_request > self.idle_seconds
        if self.idle_seconds > 0 and quiet and not self.agent.busy:
            raise _Idle


class _Handler(BaseHTTPRequestHandler):
    timeout = _SOCKET_SECONDS

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
        route, name, resource = _route(url.path)
        if self._refused(route, url.query):
            return
        if route is Route.SHELL and not name:
            self._asset(UiAsset.INDEX)
        elif resource is ApiPath.CHAT:
            self._not_allowed()
        elif route is Route.API:
            self._api(name, url.query)
        elif route is Route.UI and (asset := member(UiAsset, name)) is not None:
            self._asset(asset)
        elif route is Route.FILES and (target := self.studio.workspace.file(name)) is not None:
            kind = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            self._send(HTTPStatus.OK, target.read_bytes(), kind, csp=_FILES_CSP)
        else:
            self._send(HTTPStatus.NOT_FOUND, b"not found\n")

    def _api(self, name: str, query: str) -> None:
        prefix = f"{ApiPath.STORIES}/"
        story_id = name.removeprefix(prefix) if name.startswith(prefix) else None
        path = ApiPath.STORIES if story_id is not None else member(ApiPath, name)
        workspace = self.studio.workspace
        if path is None:
            self._send(HTTPStatus.NOT_FOUND, b"not found\n")
        elif path is ApiPath.STATE:
            self._send(
                HTTPStatus.OK,
                state_json(workspace.state(), self.studio.agent.kind),
                "application/json",
            )
        elif path is ApiPath.GRAPH:
            try:
                body = graph_json(workspace.state().explore, workspace.graph())
            except (OSError, ValueError):
                self._send(HTTPStatus.INTERNAL_SERVER_ERROR, b"the snapshot cannot be read\n")
                return
            self._send(HTTPStatus.OK, body, "application/json")
        else:
            self._stories(path, story_id, query)

    def _stories(self, path: ApiPath, story_id: str | None, query: str) -> None:
        """The story routes; a story is checked against the snapshot of this run."""
        workspace = self.studio.workspace
        stories = workspace.stories
        if stories is None:
            self._send(HTTPStatus.NOT_FOUND, b"not found\n")
        elif path is ApiPath.STORIES and story_id is None:
            state = workspace.state()
            snapshot = (
                workspace.file("architecture.json")
                if state.explore in (ExploreState.DONE, ExploreState.INCOMPLETE)
                else None
            )
            self._send(HTTPStatus.OK, stories_json(stories.rows(snapshot)), "application/json")
        else:
            snapshot = workspace.file("architecture.json")
            state = workspace.state()
            if state.explore is ExploreState.FAILED:
                detail = "\n".join(state.notes)
                message = f"explore failed (exit code {state.exit_code})"
                self._send(
                    HTTPStatus.SERVICE_UNAVAILABLE,
                    f"{message}\n{detail}\n".encode(),
                )
                return
            if state.explore is ExploreState.INCOMPLETE and path is ApiPath.DRAFT:
                self._send(
                    HTTPStatus.SERVICE_UNAVAILABLE,
                    b"cannot draft from an incomplete snapshot; UNKNOWN evidence may be missing\n",
                )
                return
            if (
                state.explore not in (ExploreState.DONE, ExploreState.INCOMPLETE)
                or snapshot is None
            ):
                self._send(HTTPStatus.SERVICE_UNAVAILABLE, b"explore has not finished\n")
                return
            try:
                if story_id is not None:
                    found = stories.find(story_id)
                    if found is None:
                        self._send(HTTPStatus.NOT_FOUND, b"not found\n")
                        return
                    checked = stories.check(found.spec, snapshot)
                    body = story_json(
                        story_id,
                        found.source,
                        checked.result,
                        rebound=checked.rebound,
                        created=provenance(found.spec),
                        head=stories.head(),
                    )
                else:
                    source = parse_qs(query).get("from", [""])[0]
                    body = draft_json(stories.draft(snapshot, source))
            except ValueError as error:
                self._send(HTTPStatus.UNPROCESSABLE_ENTITY, f"{error}\n".encode())
                return
            self._send(HTTPStatus.OK, body, "application/json")

    def _asset(self, asset: UiAsset) -> None:
        kind = mimetypes.guess_type(asset.value)[0] or "application/octet-stream"
        self._send(HTTPStatus.OK, (_UI / asset.value).read_bytes(), f"{kind}; charset=utf-8")

    def _not_allowed(self) -> None:
        allowed = "POST" if _route(urlsplit(self.path).path)[2] is ApiPath.CHAT else "GET"
        self._send(
            HTTPStatus.METHOD_NOT_ALLOWED,
            b"method not allowed\n",
            headers=(("Allow", allowed),),
        )

    do_PUT = do_DELETE = do_PATCH = _not_allowed

    def do_POST(self) -> None:
        url = urlsplit(self.path)
        route, _, resource = _route(url.path)
        if self._refused(route, url.query):
            return
        if resource is ApiPath.CHAT:
            self._chat()
        else:
            self._not_allowed()

    def _chat(self) -> None:
        """AD-292: Host and token are checked; check the origin and the header, then answer."""
        self.studio.last_request = time.monotonic()
        if (
            self.headers.get("Origin") != f"http://{self.studio.host}"
            or self.headers.get(_CHAT_HEADER) is None
        ):
            self._send(HTTPStatus.FORBIDDEN, b"forbidden\n")
            return
        try:
            self._send(HTTPStatus.OK, chat_json(self._answer()), "application/json")
        except ChatFailure as failure:
            self._send(_STATUS[failure.error], failure_json(failure), "application/json")

    def _body(self) -> bytes:
        if member(MediaType, self.headers.get_content_type()) is None:
            raise ChatFailure(
                ChatError.UNSUPPORTED_MEDIA_TYPE, "Content-Type must be application/json."
            )
        length = self.headers.get("Content-Length", "")
        if not (length.isascii() and length.isdigit()):
            raise ChatFailure(ChatError.LENGTH_REQUIRED, "Content-Length is required.")
        if int(length) > _BODY_LIMIT:
            raise ChatFailure(
                ChatError.BODY_TOO_LARGE, f"The body must have at most {_BODY_LIMIT} bytes."
            )
        return self.rfile.read(int(length))

    def _answer(self) -> ChatAnswer:
        request = parse_chat_request(self._body())
        snapshot = self.studio.workspace.snapshot()
        if snapshot is None:
            state = self.studio.workspace.state()
            if state.explore is ExploreState.INCOMPLETE:
                message = "Explore was incomplete, but no readable snapshot is available."
            elif state.explore is ExploreState.FAILED:
                message = "Explore did not produce a readable snapshot."
            else:
                message = "Explore has not finished."
            raise ChatFailure(ChatError.SNAPSHOT_NOT_READY, message)
        context = request.context
        if context is not None and not snapshot.has(context):
            raise ChatFailure(ChatError.INVALID_REQUEST, "context is no symbol of the snapshot.")
        neighborhood = snapshot.neighborhood(context) if context is not None else ""
        reply = self.studio.agent.ask(request, neighborhood, snapshot.completeness)
        if request.mode is ChatMode.STORY:
            return self._answer_story(request, snapshot, reply)
        return snapshot.check(reply.text, reply.kind)

    def _answer_story(self, request: ChatRequest, snapshot: Snapshot, reply: Reply) -> ChatAnswer:
        stories = self.studio.workspace.stories
        snapshot_path = self.studio.workspace.file("architecture.json")
        if (
            stories is None
            or snapshot_path is None
            or self.studio.workspace.snapshot() is not snapshot
        ):
            raise ChatFailure(
                ChatError.SNAPSHOT_NOT_READY,
                "The snapshot changed while the story was being drafted. Refresh and try again.",
            )
        candidate = parse_story_candidate(reply.text)
        if request.context is None:
            raise ChatFailure(
                ChatError.INVALID_REQUEST, "a story draft needs a selected starting node."
            )
        if candidate.steps[0].node != request.context:
            raise ChatFailure(
                ChatError.INVALID_ANSWER,
                "The story draft must start at the selected node.",
            )
        try:
            spec = dict(stories.draft(snapshot_path, request.context))
        except (OSError, ValueError) as error:
            raise ChatFailure(
                ChatError.SNAPSHOT_NOT_READY,
                "The current snapshot could not seed a story draft. Refresh and try again.",
            ) from error
        story = spec.get("story")
        if not isinstance(story, dict):
            raise ChatFailure(ChatError.INVALID_ANSWER, "The current snapshot cannot seed a story.")
        spec["title"] = candidate.title
        spec["nodes"] = list(dict.fromkeys(step.node for step in candidate.steps))
        spec["steps"] = [{"node": step.node, "note": step.note} for step in candidate.steps]
        story = dict(story)
        story["title"] = candidate.title
        spec["story"] = story
        spec["author_kind"] = "agent"
        spec["agent"] = reply.kind.value
        try:
            checked = stories.check(json.dumps(spec).encode(), snapshot_path).result
        except OSError as error:
            raise ChatFailure(
                ChatError.SNAPSHOT_NOT_READY,
                "The snapshot could not be checked. Refresh and try again.",
            ) from error
        except ValueError as error:
            raise ChatFailure(
                ChatError.INVALID_ANSWER,
                "The story draft could not be checked against the current snapshot.",
            ) from error
        if self.studio.workspace.snapshot() is not snapshot:
            raise ChatFailure(
                ChatError.SNAPSHOT_NOT_READY,
                "The snapshot changed while the story was being checked. Refresh and try again.",
            )
        return ChatAnswer(
            reply.kind,
            snapshot.completeness,
            (),
            (),
            (),
            StoryDraft(spec, checked),
        )


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
    workspace: Workspace,
    *,
    ready: Callable[[str], object],
    serving: Callable[[], object] | None = None,
    idle_seconds: float = 0.0,
    agent: AgentKind = AgentKind.CLAUDE,
) -> int:
    """Make the snapshot and serve until Ctrl-C or `idle_seconds` without a request (0 = never).

    `ready` gets the start URL with the token.
    """
    server = Studio(workspace, idle_seconds, agent)
    server.serving = serving
    try:
        workspace.start()
        # The caller has written its state file before the URL appears: a reader can stop us.
        ready(server.url)
        print(f"ArchKeel Studio: {server.url}\nPress Ctrl-C to stop.", flush=True)
        server.serve_forever()
    except (KeyboardInterrupt, _Idle):
        print("ArchKeel Studio: stopped.")
    finally:
        server.server_close()
        server.agent.close()
        workspace.close()
    return 0
