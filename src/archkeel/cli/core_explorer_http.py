# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Serve Studio views and user-requested story creation on loopback."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from urllib.parse import parse_qsl, urlsplit

from archkeel.explorer_agent import _create_story
from archkeel.explorer_queries import query
from archkeel.explorer_stories import list_stories, read_story

from .core_frame import CoreError

_ASSETS = Path(__file__).with_name("assets")
_ROUTES = {
    "/": ("explorer.html", "text/html; charset=utf-8"),
    "/studio-api.js": ("studio-api.js", "text/javascript; charset=utf-8"),
    "/studio-dom.js": ("studio-dom.js", "text/javascript; charset=utf-8"),
    "/studio-state.js": ("studio-state.js", "text/javascript; charset=utf-8"),
    "/explorer.js": ("explorer.js", "text/javascript; charset=utf-8"),
    "/explorer-navigation.js": ("explorer-navigation.js", "text/javascript; charset=utf-8"),
    "/explorer-uml.js": ("explorer-uml.js", "text/javascript; charset=utf-8"),
    "/explorer-tree.js": ("explorer-tree.js", "text/javascript; charset=utf-8"),
    "/explorer-story.js": ("explorer-story.js", "text/javascript; charset=utf-8"),
    "/explorer-story-loading.js": ("explorer-story-loading.js", "text/javascript; charset=utf-8"),
    "/explorer-story-routes.js": ("explorer-story-routes.js", "text/javascript; charset=utf-8"),
    "/explorer-story.css": ("explorer-story.css", "text/css; charset=utf-8"),
    "/explorer-map.js": ("explorer-map.js", "text/javascript; charset=utf-8"),
    "/explorer-map.css": ("explorer-map.css", "text/css; charset=utf-8"),
    "/explorer-map-layout.js": ("explorer-map-layout.js", "text/javascript; charset=utf-8"),
    "/report-layout.js": ("report-layout.js", "text/javascript; charset=utf-8"),
    "/report-placement.js": ("report-placement.js", "text/javascript; charset=utf-8"),
    "/elkjs-0.12.0.bundled.js": ("elkjs-0.12.0.bundled.js", "text/javascript; charset=utf-8"),
    "/explorer.css": ("explorer.css", "text/css; charset=utf-8"),
}
_OPERATIONS = frozenset(
    {"overview", "children", "search", "relations", "evidence", "source", "story", "map"}
)
_CSP = (
    "default-src 'none'; script-src 'self'; style-src 'self'; font-src data:; "
    "connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
)


class _ExplorerServer(ThreadingHTTPServer):
    # A browser loads the Studio module graph in parallel.
    request_queue_size = 64

    def __init__(
        self,
        path: Path,
        root: Path,
        report: Callable[[], tuple[str, tuple[str, bytes]]] | None,
        port: int,
        confirm: Callable[[], None] | None = None,
    ) -> None:
        self.snapshot = path
        self.root = root
        self.report = report
        self.confirm = confirm
        self.chat_lock = Lock()
        self.report_lock = Lock()
        tokens = _ASSETS / "explorer-tokens.css"
        if not tokens.is_file():
            tokens = _ASSETS.parents[3] / "native/report/assets/tokens.css"
        self.css = tokens.read_bytes()
        # A running server must serve the client that matches its query protocol.
        self.assets: dict[str, tuple[bytes, str]] = {}
        for route, (file, content) in _ROUTES.items():
            asset = _ASSETS / file
            if not asset.is_file() and file in {
                "report-layout.js",
                "report-placement.js",
                "elkjs-0.12.0.bundled.js",
            }:
                asset = _ASSETS.parents[3] / "native/report/assets/explorer" / file
            self.assets[route] = asset.read_bytes(), content
        super().__init__(("127.0.0.1", port), _Browse)


class _Browse(BaseHTTPRequestHandler):
    server: _ExplorerServer

    def setup(self) -> None:
        self.request.settimeout(5)
        super().setup()

    def log_message(self, format: str, *args: object) -> None:
        """Keep source references and searches out of logs."""

    def _reply(
        self,
        code: int,
        body: bytes,
        content: str = "text/plain; charset=utf-8",
        *,
        csp: str = _CSP,
    ) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", csp)
        self.end_headers()
        self.wfile.write(body)

    def _local(self, *, write: bool = False) -> bool:
        host = f"127.0.0.1:{self.server.server_port}"
        origin = self.headers.get_all("Origin")
        allowed_origins = ([f"http://{host}"],) if write else (None, [f"http://{host}"])
        return (
            self.headers.get_all("Host") == [host]
            and origin in allowed_origins
            and self.headers.get("Sec-Fetch-Site") in {None, "none", "same-origin"}
        )

    def _json(self, status: int, value: object) -> None:
        self._reply(status, json.dumps(value).encode(), "application/json; charset=utf-8")

    def do_POST(self) -> None:
        if self.path != "/api/v1/story-chat":
            self._reply(405, b"Method not allowed.")
            return
        if not self._local(write=True):
            self._json(403, {"error": "Open the chat from the local Studio page."})
            return
        if self.headers.get_content_type() != "application/json":
            self._json(415, {"error": "Send a JSON chat request."})
            return
        try:
            lengths = self.headers.get_all("Content-Length") or []
            if len(lengths) != 1 or self.headers.get("Transfer-Encoding"):
                raise ValueError("A single content length is required.")
            size = int(lengths[0])
            if not 0 < size <= 32_768:
                raise ValueError("The chat request must fit in 32 KiB.")
            data = json.loads(self.rfile.read(size))
            if not isinstance(data, dict) or data.keys() - {"prompt", "element", "story"}:
                raise ValueError("Expected a prompt and optional element or story.")
            prompt, element, story = (data.get(k, "") for k in ("prompt", "element", "story"))
            if not all(isinstance(v, str) for v in (prompt, element, story)) or not prompt.strip():
                raise ValueError("Enter a flow to explain.")
            if not self.server.chat_lock.acquire(blocking=False):
                self._json(409, {"error": "A story is being prepared. Wait for it to finish."})
                return
            try:
                if self.server.confirm:
                    self.server.confirm()
                result = _create_story(
                    self.server.root,
                    self.server.snapshot,
                    prompt,
                    element,
                    story,
                    confirm=self.server.confirm,
                )
            finally:
                self.server.chat_lock.release()
        except CoreError:
            self._json(409, {"error": "The project changed. Open Studio again to scan it."})
        except ValueError as error:
            self._json(400, {"error": str(error)})
        except RuntimeError as error:
            self._json(503, {"error": str(error)})
        except (OSError, sqlite3.Error):
            self._json(409, {"error": "Studio could not read the snapshot or save the story."})
        else:
            self._json(201, result)

    def do_GET(self) -> None:
        if not self._local():
            self._reply(403, b"Open the Explorer from its local URL.")
            return
        try:
            url = urlsplit(self.path)
            if url.netloc or url.scheme or len(self.path) > 4096:
                raise ValueError("invalid request")
            operation = url.path.removeprefix("/api/").removeprefix("v1/")
            if url.path in self.server.assets:
                self._reply(200, *self.server.assets[url.path])
            elif url.path == "/api/v1/stories":
                self._stories(parse_qsl(url.query, keep_blank_values=True, strict_parsing=True))
            elif url.path == "/report":
                self._native_report()
            elif url.path.startswith("/archkeel-gaps-") and url.path.endswith(".json"):
                self._report_gaps(url.path)
            elif url.path == "/report.css":
                self._reply(200, self.server.css, "text/css; charset=utf-8")
            elif url.path.startswith("/api/") and operation in _OPERATIONS:
                self._api(operation, url.query)
            else:
                self._reply(404, b"Page not found.")
        except ValueError:
            self._reply(400, b"Invalid Explorer request.")
        except (OSError, CoreError):
            self._reply(409, b"The report is unavailable for this snapshot. Restart the Explorer.")

    def _stories(self, args: list[tuple[str, str]]) -> None:
        try:
            if not args:
                result: dict[str, object] = {
                    "items": list_stories(self.server.root, self.server.snapshot)
                }
            elif len(args) == 1 and args[0][0] == "id":
                result = read_story(self.server.root, self.server.snapshot, args[0][1])
            else:
                raise ValueError("invalid story request")
        except ValueError as error:
            self._reply(400, f"Story: {error}.".encode())
        except (OSError, sqlite3.Error):
            self._reply(409, b"Studio could not read the story or its snapshot.")
        else:
            self._json(200, result)

    def _native_report(self) -> None:
        if self.server.report is None:
            self._reply(404, b"The observed-only snapshot has no architecture contract report.")
            return
        link = '<a class="ui" href="/">Open architecture whiteboard</a>'
        with self.server.report_lock:
            page, _ = self.server.report()
        page = page.replace("</header>", link + "</header>", 1)
        self._reply(
            200,
            page.encode(),
            "text/html; charset=utf-8",
            csp="base-uri 'none'; frame-ancestors 'none'",
        )

    def _report_gaps(self, path: str) -> None:
        if self.server.report is None:
            self._reply(404, b"Page not found.")
            return
        with self.server.report_lock:
            _, (name, content) = self.server.report()
        if path != "/" + name:
            self._reply(404, b"Page not found.")
            return
        self._reply(200, content, "application/json; charset=utf-8")

    def _api(self, operation: str, query_string: str) -> None:
        pairs = parse_qsl(query_string, keep_blank_values=True, max_num_fields=12)
        arguments: dict[str, object] = dict(pairs)
        if len(arguments) != len(pairs):
            raise ValueError("repeated argument")
        try:
            result = query(self.server.snapshot, self.server.root, operation, arguments)
        except (OSError, ValueError, sqlite3.Error) as error:
            if operation == "source":
                reason = str(error) if isinstance(error, ValueError) else "source cannot be read"
                self._reply(409, f"Snapshot source unavailable: {reason}.".encode())
            elif isinstance(error, ValueError):
                self._reply(400, f"Explorer {operation}: {error}.".encode())
            else:
                self._reply(
                    409, b"Studio could not read the snapshot. Restart Studio to scan again."
                )
            return
        self._reply(200, json.dumps(result).encode(), "application/json; charset=utf-8")
