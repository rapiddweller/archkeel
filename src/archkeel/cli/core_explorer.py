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
from pathlib import Path

from archkeel.explorer_queries import populate
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
from .core_explorer_http import _ExplorerServer
from .core_explorer_identity import _file_digest, _fingerprint
from .core_explorer_scip import ScipIndex, enrich
from .core_frame import CoreError, CoreFrame, GapKind
from .core_json import as_object, as_text
from .init_draft import draft, write_missing
from .native_scan import prepare_disposable_git

_REPORT_CACHE_BYTES = 64 << 20


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
    scip: ScipIndex | None,
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

    if scip is not None:
        enrich(scip, binary, project.path, digests, topology)

    def build(connection: sqlite3.Connection) -> None:
        display = topology | {
            "verdict": None if observed else frame.status.value,
            "observed_only": observed,
        }
        populate(connection, display, project.path)
        if _current_identity(project, binary, scip) != snapshot:
            raise CoreError("the project changed during the Explorer scan; run explore again")

    publish_snapshot(path, snapshot, build, coverage)


def _current_identity(
    project: ProjectRoot, binary: Path, scip: ScipIndex | None
) -> SnapshotIdentity:
    identity, _ = _fingerprint(project, binary)
    if scip is None:
        return identity
    scip.confirm()
    return scip.bind(identity)


def launch(
    options: Options,
    mode: OutputMode,
    project: ProjectRoot,
    binary: Path,
    scan: Callable[[ProjectRoot], tuple[bytes, CoreFrame]],
    render_report: Callable[[], tuple[str, tuple[str, bytes]]] | None,
) -> int:
    """Use a matching snapshot or publish a new one, then start the local Explorer."""
    scip = ScipIndex.read(options.scip_index) if options.scip_index is not None else None
    snapshot, digests = _fingerprint(project, binary)
    if scip is not None:
        snapshot = scip.bind(snapshot)
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
                    path,
                    project,
                    binary,
                    snapshot,
                    digests,
                    scan,
                    observed=render_report is None,
                    scip=scip,
                )

    def confirm_snapshot() -> None:
        if _current_identity(project, binary, scip) != snapshot:
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
            path, project.path, report if render_report else None, options.port, confirm_snapshot
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
