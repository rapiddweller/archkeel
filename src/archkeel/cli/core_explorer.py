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
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path

from archkeel.explorer_queries import populate
from archkeel.explorer_store import (
    SnapshotIdentity,
    cache_path,
    open_snapshot,
    publish_snapshot,
    repository_writer,
)
from archkeel.explorer_verdict import Basis, Finding, Unknown, VerdictRows

from .core_arguments import Options, OutputMode
from .core_binding import ProjectRoot
from .core_exit import Outcome, envelope, exit_for
from .core_explorer_http import _ExplorerServer
from .core_explorer_identity import _file_digest, _fingerprint
from .core_explorer_scip import (
    ScipIndex,
    ScipLoadError,
    _discover_rust_index,
    _store_resolution,
)
from .core_frame import CoreError, CoreFrame, GapKind, RuleStatus
from .core_json import as_object, as_text, as_texts
from .core_topology import Topology
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


def _verdict_rows(
    frame: CoreFrame,
    topology: Topology,
    document: Mapping[str, object],
    sources: Mapping[str, str],
) -> VerdictRows:
    """Copy the verdict rows of the frame. The core decided them; nothing is decided again."""
    owners = {module.name: module.component for module in topology.modules}
    parents = {component.id: component.parent for component in topology.components}
    # A cycle names its members by component name, and a module names its component by id.
    ids = {
        name: component.id
        for component in topology.components
        for name in (component.name, component.id)
    }

    def lineage(name: str) -> Iterator[str]:
        """The component of a module or a component name, then each parent of it."""
        current = ids.get(owners.get(name) or name)
        while current is not None:
            yield current
            current = parents.get(current)

    def place(keys: tuple[str, ...]) -> str | None:
        return next(
            (f"{found.path}:{found.line}" for key in keys if (found := frame.locations.get(key))),
            None,
        )

    findings = tuple(
        Finding(
            rule,
            detail.source if detail.target is None else f"{detail.source} -> {detail.target}",
            place(detail.evidence),
            Basis.DECLARED if detail.possible else Basis.PROVEN,
            tuple(
                sorted(
                    {
                        found
                        for name in detail.members or (detail.source, detail.target or "")
                        for found in lineage(name)
                    }
                )
            ),
        )
        for rule, details in frame.details.items()
        for detail in details
    )
    unknowns = (
        *(Unknown(gap.kind, gap.subject, gap.reason, None) for gap in frame.gaps),
        *(
            Unknown(gap.kind, ", ".join(gap.subjects), gap.reason, place(gap.evidence))
            for gap in frame.collection_gaps
        ),
    )
    digest = document.get("contract_digest")
    return VerdictRows(
        frame.status.value,
        exit_for(Outcome.VERDICT, frame, baseline=False),
        sum(1 for count in frame.violations.values() if count),
        sum(1 for verdict in frame.rules.values() if verdict.status is RuleStatus.UNKNOWN),
        None if digest is None else as_text(digest, "contract_digest"),
        as_texts(document.get("rule_rationales", {}), "rule_rationales"),
        findings,
        unknowns,
        sources,
    )


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

    # An observed scan runs against a drafted contract, so it has no verdict to keep.
    rows = None
    if not observed:
        config = Path(project.config).as_posix()
        sources = {
            name: digests[name]
            for name in sorted({*paths, config})
            if len(digests.get(name, "")) == 64
        }
        rows = _verdict_rows(frame, frame.topology, document, sources)

    def build(connection: sqlite3.Connection) -> None:
        display = topology | {
            "verdict": None if observed else frame.status.value,
            "observed_only": observed,
        }
        populate(connection, display, project.path, rows)
        if scip is not None:
            _store_resolution(connection, scip, binary, project.path, digests, topology)
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


def _bind_artifact(
    path: Path | None, snapshot: SnapshotIdentity
) -> tuple[ScipIndex | None, SnapshotIdentity]:
    if path is None:
        return None, snapshot
    artifact = ScipIndex.read(path)
    return artifact, artifact.bind(snapshot)


def _resolve_scip(
    options: Options, root: Path, snapshot: SnapshotIdentity
) -> tuple[ScipIndex | None, SnapshotIdentity, bool]:
    if options.scip_index is not None:
        artifact, bound = _bind_artifact(options.scip_index, snapshot)
        return artifact, bound, True
    if options.no_scip:
        return None, snapshot, False
    discovered = _discover_rust_index(root)
    if discovered is None:
        return None, snapshot, False
    try:
        artifact, bound = _bind_artifact(discovered, snapshot)
    except ScipLoadError as error:
        print(f"SCIP index {discovered} skipped ({error}); using native scan", file=sys.stderr)
        return None, snapshot, False
    return artifact, bound, False


def _cache_location(root: Path, snapshot: SnapshotIdentity) -> Path:
    default = Path.home() / ".cache"
    cache = (Path(os.environ.get("XDG_CACHE_HOME") or default) / "archkeel" / "explorer").resolve()
    if cache.is_relative_to(root):
        raise CoreError("the Explorer cache must be outside the project root")
    return cache_path(cache, root, snapshot)


def _ensure_snapshot(
    project: ProjectRoot,
    binary: Path,
    snapshot: SnapshotIdentity,
    digests: dict[str, str],
    scan: Callable[[ProjectRoot], tuple[bytes, CoreFrame]],
    *,
    observed: bool,
    scip: ScipIndex | None,
) -> Path:
    path = _cache_location(project.path, snapshot)
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
                    observed=observed,
                    scip=scip,
                )
    return path


def _prepare_snapshot(
    options: Options,
    project: ProjectRoot,
    binary: Path,
    scan: Callable[[ProjectRoot], tuple[bytes, CoreFrame]],
    *,
    observed: bool,
) -> tuple[Path, SnapshotIdentity, ScipIndex | None]:
    base_snapshot, digests = _fingerprint(project, binary)
    scip, snapshot, explicit = _resolve_scip(options, project.path, base_snapshot)
    try:
        path = _ensure_snapshot(
            project, binary, snapshot, digests, scan, observed=observed, scip=scip
        )
    except ScipLoadError as error:
        if explicit or scip is None:
            raise
        print(f"SCIP index {scip.path} skipped ({error}); using native scan", file=sys.stderr)
        scip = None
        snapshot = base_snapshot
        path = _ensure_snapshot(
            project, binary, snapshot, digests, scan, observed=observed, scip=None
        )
    return path, snapshot, scip


def launch(
    options: Options,
    mode: OutputMode,
    project: ProjectRoot,
    binary: Path,
    scan: Callable[[ProjectRoot], tuple[bytes, CoreFrame]],
    render_report: Callable[[], tuple[str, tuple[str, bytes]]] | None,
) -> int:
    """Use a matching snapshot or publish a new one, then start the local Explorer."""
    scip_possible = options.scip_index is not None or (
        not options.no_scip and _discover_rust_index(project.path) is not None
    )
    try:
        path, snapshot, scip = _prepare_snapshot(
            options, project, binary, scan, observed=render_report is None
        )
    except KeyboardInterrupt:
        if not scip_possible:
            raise
        return 130

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
