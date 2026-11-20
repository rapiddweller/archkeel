# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Publish a verified native report and serve its snapshot on loopback."""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
import tempfile
import webbrowser
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

from archkeel.explorer_queries import populate, query
from archkeel.explorer_store import (
    SnapshotIdentity,
    cache_path,
    open_snapshot,
    publish_snapshot,
    repository_writer,
)

from .core_arguments import Options, OutputMode
from .core_binding import ProjectRoot
from .core_exit import Outcome, envelope, exit_for
from .core_explorer_identity import _file_digest, _fingerprint
from .core_frame import CoreError, CoreFrame, GapKind
from .core_json import as_object, as_text
from .init_draft import draft, write_missing
from .native_scan import prepare_disposable_git

_ASSETS = Path(__file__).with_name("assets")
_REPORT_CACHE_BYTES = 64 << 20
_ROUTES = {
    "/": ("explorer.html", "text/html; charset=utf-8"),
    "/explorer.js": ("explorer.js", "text/javascript; charset=utf-8"),
    "/explorer-uml.js": ("explorer-uml.js", "text/javascript; charset=utf-8"),
    "/explorer-story.js": ("explorer-story.js", "text/javascript; charset=utf-8"),
    "/explorer.css": ("explorer.css", "text/css; charset=utf-8"),
}
_OPERATIONS = frozenset(
    {"overview", "children", "search", "relations", "evidence", "source", "story"}
)
_CSP = (
    "default-src 'none'; script-src 'self'; style-src 'self'; font-src data:; "
    "connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
)


class _ExplorerServer(HTTPServer):
    def __init__(
        self,
        path: Path,
        root: Path,
        report: Callable[[], tuple[str, tuple[str, bytes]]] | None,
        port: int,
    ) -> None:
        self.snapshot = path
        self.root = root
        self.report = report
        tokens = _ASSETS / "explorer-tokens.css"
        if not tokens.is_file():
            tokens = _ASSETS.parents[3] / "native/report/assets/tokens.css"
        self.css = tokens.read_bytes()
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

    def do_GET(self) -> None:
        host = f"127.0.0.1:{self.server.server_port}"
        if (
            self.headers.get_all("Host") != [host]
            or self.headers.get("Origin") not in {None, f"http://{host}"}
            or self.headers.get("Sec-Fetch-Site") not in {None, "none", "same-origin"}
        ):
            self._reply(403, b"Open the Explorer from its local URL.")
            return
        try:
            url = urlsplit(self.path)
            if url.netloc or url.scheme or len(self.path) > 4096:
                raise ValueError("invalid request")
            operation = url.path.removeprefix("/api/").removeprefix("v1/")
            if url.path in _ROUTES:
                file, content = _ROUTES[url.path]
                self._reply(200, (_ASSETS / file).read_bytes(), content)
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

    def _native_report(self) -> None:
        if self.server.report is None:
            self._reply(404, b"The observed-only snapshot has no architecture contract report.")
            return
        link = '<a class="ui" href="/">Open architecture whiteboard</a>'
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
            else:
                self._reply(400, b"The requested Explorer data is unavailable.")
            return
        self._reply(200, json.dumps(result).encode(), "application/json; charset=utf-8")


def _observed_scan(
    project: ProjectRoot,
    digests: dict[str, str],
    scan: Callable[[ProjectRoot], tuple[bytes, CoreFrame]],
) -> tuple[bytes, CoreFrame]:
    if Path(tempfile.gettempdir()).resolve().is_relative_to(project.path):
        raise CoreError("the Explorer temporary directory must be outside the project root")
    with tempfile.TemporaryDirectory(prefix="archkeel-observed-") as temporary:
        copy = Path(temporary).resolve() / project.path.name
        copy.mkdir()
        for name, digest in digests.items():
            if len(digest) != 64:
                continue  # Git paths that are missing, links or submodule directories.
            original, target = project.path / name, copy / name
            if original.resolve() != original or not original.is_file():
                raise CoreError("a project file changed before the observed scan")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(original, target)
            if _file_digest(target) != digest:
                raise CoreError("a project file changed while copying the observed scan")
        # Isolate scanner inputs from repository documentation with the same filenames.
        folder = ".archkeel-observed"
        while (copy / folder).exists():
            folder += "_"
        layout = draft(copy, scan_folder=folder)
        write_missing(copy, layout)
        prepare_disposable_git(copy)
        return scan(ProjectRoot.of(copy, layout.entry))


def _publish(
    path: Path,
    project: ProjectRoot,
    binary: Path,
    snapshot: SnapshotIdentity,
    digests: dict[str, str],
    scan: Callable[[ProjectRoot], tuple[bytes, CoreFrame]],
    *,
    observed: bool,
) -> None:
    stdout, frame = _observed_scan(project, digests, scan) if observed else scan(project)
    refused = next((gap for gap in frame.gaps if gap.kind is GapKind.COLLECT), None)
    if frame.topology is None:
        raise CoreError(refused.reason if refused else "the core did not give Explorer topology")
    document = as_object(json.loads(stdout), "frame")
    topology = dict(as_object(document["topology"], "frame.topology"))
    topology["explorer"] = document.get("explorer", [])
    topology["locations"] = document.get("locations", {})
    if "system" in document and not observed:
        system = as_object(document["system"], "frame.system")
        rows = system.get("interfaces")
        if not isinstance(rows, list):
            raise CoreError("the core frame has invalid system interfaces")
        parts = {
            component.id for component in frame.topology.components if component.parent is None
        }
        interfaces = []
        for item in rows:
            fields = as_object(item, "system.interfaces[]")
            row = {
                key: as_text(fields[key], f"system.interfaces.{key}")
                for key in (
                    "id",
                    "source",
                    "target",
                    "title",
                    "schema",
                )
            }
            if f"PART:{row['source']}" in parts and f"PART:{row['target']}" in parts:
                interfaces.append(row)
        topology["interfaces"] = interfaces
    collect = as_object(as_object(document["self_test"], "self_test")["collect"], "collect")
    contract_files = as_object(collect["contract_files"], "contract_files")
    paths = {module.path for module in frame.topology.modules}
    if not observed:
        paths.update(contract_files)
    if any(len(digests.get(path, "")) != 64 for path in paths):
        raise CoreError("some assessed files are outside the Explorer fingerprint")
    coverage = "complete" if frame.topology.complete and not frame.topology.truncated else "UNKNOWN"

    if observed:
        topology["requires"] = []
        for section, drop in (
            ("components", ("responsibilities", "forbidden_responsibilities", "public")),
            ("edges", ("rules",)),
            ("component_edges", ("rules",)),
        ):
            rows = topology[section]
            if not isinstance(rows, list):
                raise CoreError(f"invalid topology section {section}")
            topology[section] = [
                {key: value for key, value in as_object(row, section).items() if key not in drop}
                for row in rows
            ]

    def build(connection: sqlite3.Connection) -> None:
        display = topology | {
            "verdict": None if observed else frame.status.value,
            "observed_only": observed,
        }
        populate(connection, display, project.path)
        if _fingerprint(project, binary)[0] != snapshot:
            raise CoreError("the project changed during the Explorer scan; run explore again")

    publish_snapshot(path, snapshot, build, coverage)


def launch(
    options: Options,
    mode: OutputMode,
    project: ProjectRoot,
    binary: Path,
    scan: Callable[[ProjectRoot], tuple[bytes, CoreFrame]],
    render_report: Callable[[], tuple[str, tuple[str, bytes]]] | None,
) -> int:
    """Use a matching snapshot or publish a new one, then start the local Explorer."""
    snapshot, digests = _fingerprint(project, binary)
    default = Path.home() / ".cache"
    cache = Path(os.environ.get("XDG_CACHE_HOME") or default) / "archkeel" / "explorer"
    cache = cache.resolve()
    if cache.is_relative_to(project.path):
        raise CoreError("the Explorer cache must be outside the project root")
    path = cache_path(cache, project.path, snapshot)
    if not path.exists():
        with repository_writer(path):
            if not path.exists():
                _publish(
                    path, project, binary, snapshot, digests, scan, observed=render_report is None
                )

    def confirm_snapshot() -> None:
        if _fingerprint(project, binary)[0] != snapshot:
            raise CoreError("the project changed after the Explorer scan; run explore again")

    cached_report: tuple[str, tuple[str, bytes]] | None = None

    def report() -> tuple[str, tuple[str, bytes]]:
        nonlocal cached_report
        confirm_snapshot()
        if render_report is None:
            raise CoreError("the core did not give the native report")
        if cached_report is None:
            result = render_report()
            confirm_snapshot()
            if len(result[0].encode("utf-8")) + len(result[1][1]) <= _REPORT_CACHE_BYTES:
                cached_report = result
            return result
        return cached_report

    code = exit_for(Outcome.COMPLETED, None, baseline=False)
    with (
        open_snapshot(path, snapshot),
        _ExplorerServer(
            path, project.path, report if render_report else None, options.port
        ) as server,
    ):
        confirm_snapshot()
        url = f"http://127.0.0.1:{server.server_port}/"
        if mode is OutputMode.JSON:
            result = envelope("explore", Outcome.COMPLETED, None, code) | {
                "url": url,
                "snapshot": str(path),
                "root": str(project.path),
            }
            print(json.dumps(result), flush=True)
        else:
            print(
                f"ArchKeel Explorer: {url} (Ctrl-C to stop)\n"
                f"Snapshot: {path}\nRoot: {project.path}",
                flush=True,
            )
        if not options.no_open:
            try:
                webbrowser.open(url)
            except (OSError, webbrowser.Error) as error:
                print(f"Open {url} in your browser: {error}", file=sys.stderr)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
    return code
