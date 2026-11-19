# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Publish a verified native report and serve its snapshot on loopback."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import stat
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
from .core_binary import collector_workers
from .core_binding import ProjectRoot
from .core_exit import Outcome, envelope, exit_for
from .core_frame import CoreError, CoreFrame, GapKind
from .core_json import as_object, as_text
from .init_draft import draft, write_missing
from .native_scan import identity, prepare_disposable_git, tracked_and_unignored

_ASSETS = Path(__file__).with_name("assets")
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
    def __init__(self, path: Path, root: Path, report: Callable[[], str] | None, port: int) -> None:
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
        page = self.server.report().replace("</header>", link + "</header>", 1)
        self._reply(
            200,
            page.encode(),
            "text/html; charset=utf-8",
            csp="base-uri 'none'; frame-ancestors 'none'",
        )

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


def _file_digest(file: Path, info: os.stat_result | None = None) -> str:
    expected = info or file.lstat()
    flags = os.O_RDONLY
    if sys.platform != "win32":
        flags |= os.O_NOFOLLOW | os.O_NONBLOCK
    descriptor = os.open(file, flags)
    with os.fdopen(descriptor, "rb") as opened:
        before = os.fstat(opened.fileno())
        if not stat.S_ISREG(before.st_mode) or (
            before.st_dev,
            before.st_ino,
            before.st_mtime_ns,
            before.st_ctime_ns,
        ) != (expected.st_dev, expected.st_ino, expected.st_mtime_ns, expected.st_ctime_ns):
            raise CoreError("a fingerprint input was replaced or is not a regular file")
        digest = hashlib.file_digest(opened, "sha256").hexdigest()
        after = os.fstat(opened.fileno())
        if (before.st_mtime_ns, before.st_ctime_ns) != (after.st_mtime_ns, after.st_ctime_ns):
            raise CoreError("a fingerprint input changed during the read")
        return digest


def _fingerprint(project: ProjectRoot, binary: Path) -> tuple[SnapshotIdentity, dict[str, str]]:
    state = identity(project.path)
    if state is None:
        raise CoreError("the Explorer needs a Git work tree with a commit")
    files = tracked_and_unignored(project.path) | {Path(project.config)}
    digests: dict[str, str] = {}
    total = 0
    for name in sorted(files):
        file = project.path / name
        if name.is_absolute() or ".." in name.parts:
            raise CoreError("an Explorer snapshot path leaves the project root")
        if file.parent.resolve() != file.parent:
            raise CoreError("an Explorer snapshot path has a linked parent")
        try:
            info = file.lstat()
        except FileNotFoundError:
            digests[name.as_posix()] = "missing"
            continue
        if stat.S_ISLNK(info.st_mode):
            digests[name.as_posix()] = "link:" + os.readlink(file)
        elif stat.S_ISREG(info.st_mode):
            total += info.st_size
            if total > 2 << 30:
                raise CoreError("the Explorer snapshot exceeds the 2 GiB fingerprint limit")
            digests[name.as_posix()] = _file_digest(file, info)
        elif stat.S_ISDIR(info.st_mode):
            digests[name.as_posix()] = "directory"
        else:
            raise CoreError("the Explorer snapshot contains an unsupported file")
    source = hashlib.sha256(json.dumps([state[1], digests], sort_keys=True).encode()).hexdigest()
    executables = [
        (_file_digest(path) if path.exists() else "missing")
        for path in (binary, *collector_workers(binary))
    ]
    contract = hashlib.sha256(json.dumps([project.config, executables]).encode()).hexdigest()
    return SnapshotIdentity(state[0], contract, source), digests


def _observed_scan(
    project: ProjectRoot,
    digests: dict[str, str],
    scan: Callable[[ProjectRoot], tuple[bytes, CoreFrame]],
) -> tuple[bytes, CoreFrame]:
    if Path(tempfile.gettempdir()).resolve().is_relative_to(project.path):
        raise CoreError("the Explorer temporary directory must be outside the project root")
    with tempfile.TemporaryDirectory(prefix="archkeel-observed-") as temporary:
        copy = Path(temporary).resolve()
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
        layout = draft(copy)
        written = write_missing(copy, layout)
        if len(written) != len(layout.files):
            raise CoreError("existing architecture files require an explicit --config")
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
    render_report: Callable[[], str | None] | None,
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

    def report() -> str:
        confirm_snapshot()
        page = render_report() if render_report is not None else None
        confirm_snapshot()
        if page is None:
            raise CoreError("the core did not give the native report")
        return page

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
