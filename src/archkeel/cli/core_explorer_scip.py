# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Store optional checked call evidence alongside the native Explorer projection."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import stat
import tempfile
import tomllib
from collections.abc import Iterator
from dataclasses import dataclass, replace
from pathlib import Path
from typing import BinaryIO

from archkeel.explorer_store import SnapshotIdentity

from .core_binary import collector_workers, confirm
from .core_explorer_identity import _file_digest
from .core_json import CoreError, as_count, as_object, as_text, as_text_list, as_texts
from .native_scan import exchange

_INDEX_LIMIT = 64 << 20
_MANIFEST_LIMIT = 8 << 20
_REQUEST_LIMIT = 16 << 20
_REPLY_LIMIT = 64 << 20
_ROW_LIMIT = 64 << 10
_STDLIB = {"core", "alloc", "std"}
_MACRO = "Macro expansion can contain calls that are not read"
_SCHEMA = (
    "CREATE TABLE scip_artifact(index_sha256 TEXT PRIMARY KEY, manifest_sha256 TEXT)",
    """
CREATE TABLE call_resolution(
    call_id TEXT PRIMARY KEY, language TEXT NOT NULL, status TEXT NOT NULL,
    provenance TEXT, reason TEXT, canonical_target_definition_id TEXT, dispatch_kind TEXT,
    evidence_id TEXT, declaration_path TEXT, declaration_line INTEGER,
    crate_name TEXT, crate_version TEXT, symbol_path TEXT,
    reference_path TEXT, reference_start_line INTEGER, reference_start_column INTEGER,
    reference_end_line INTEGER, reference_end_column INTEGER
)""",
    """
CREATE TABLE call_resolution_count AS
SELECT language, status, provenance, reason, count(*) AS count
FROM call_resolution GROUP BY language, status, provenance, reason
ORDER BY language, status, provenance, reason""",
)
Row = dict[str, object]


def _artifact_digest(path: Path, limit: int) -> str:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= limit:
        raise CoreError(
            f"SCIP artifact is not a regular nonempty file within its size limit: {path}"
        )
    return _file_digest(path, info)


@dataclass(frozen=True)
class ScipIndex:
    """The exact index and optional manifest that bind one Explorer snapshot."""

    path: Path
    manifest: Path
    index_sha256: str
    manifest_sha256: str | None

    @classmethod
    def read(cls, requested: Path) -> ScipIndex:
        """Bind the regular artifact files without following a final symlink."""
        path = requested.parent.resolve() / requested.name
        manifest = path.with_name(path.name + ".manifest.json")
        index_sha256 = _artifact_digest(path, _INDEX_LIMIT)
        try:
            manifest_sha256 = _artifact_digest(manifest, _MANIFEST_LIMIT)
        except FileNotFoundError:
            manifest_sha256 = None
        return cls(path, manifest, index_sha256, manifest_sha256)

    def bind(self, identity: SnapshotIdentity) -> SnapshotIdentity:
        """Keep the cache entry specific to this evidence schema and artifact."""
        contract = json.dumps(
            [identity.contract, "scip-evidence-2", self.index_sha256, self.manifest_sha256]
        )
        return replace(identity, contract=hashlib.sha256(contract.encode()).hexdigest())

    def confirm(self) -> None:
        """Verify the artifact again before a cached or newly built view opens."""
        if self != self.read(self.path):
            raise CoreError("the SCIP artifacts changed during the Explorer launch")


def _rows(value: object, field: str) -> Iterator[Row]:
    if value is None:
        return
    if not isinstance(value, list):
        raise CoreError(f"invalid SCIP {field} records")
    for row in value:
        yield as_object(row, field)


def _location(locations: Row, evidence: str) -> tuple[str, int]:
    site = as_object(locations.get(evidence), "SCIP source location")
    path = as_text(site.get("path"), "SCIP source path")
    line = as_count(site.get("line"), "SCIP source line")
    if line < 1:
        raise CoreError("invalid SCIP source line")
    return path, line


def _inputs(topology: Row) -> tuple[list[Row], list[Row], Row]:
    locations = as_object(topology.get("locations"), "locations")
    parts = [p for p in _rows(topology.get("explorer"), "parts") if p.get("language") == "rust"]
    if not parts or all(part.get("calls") is None for part in parts):
        raise CoreError("SCIP evidence requires a Rust Explorer scan with call records")
    calls: list[Row] = []
    definitions: list[Row] = []
    for part in parts:
        calls.extend(_rows(part.get("calls"), "calls"))
        for symbol in _rows(part.get("symbols"), "symbols"):
            if symbol.get("kind") not in ("function", "method") or not symbol.get("qualified_name"):
                continue
            evidence = as_text_list(symbol.get("evidence_ids"), "definition evidence")
            if len(evidence) == 1:
                definitions.append(
                    dict(id=symbol["id"], evidence_id=evidence[0], kind=symbol["kind"])
                )
    return calls, definitions, locations


def _packages(root: Path, paths: set[str], digests: dict[str, str]) -> list[str]:
    manifests: set[Path] = set()
    for path in paths:
        for parent in Path(path).parents:
            manifest = parent / "Cargo.toml"
            if manifest.as_posix() in digests:
                manifests.add(manifest)
                break
    names: set[str] = set()
    for manifest in sorted(manifests):
        file = root / manifest
        try:
            if file.resolve() != file:
                raise CoreError("invalid Cargo manifest in the Explorer source fingerprint")
            flags = os.O_RDONLY if os.name == "nt" else os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
            with os.fdopen(os.open(file, flags), "rb") as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_size > 1 << 20:
                    raise CoreError("invalid Cargo manifest in the Explorer source fingerprint")
                data = stream.read((1 << 20) + 1)
            if hashlib.sha256(data).hexdigest() != digests[manifest.as_posix()]:
                raise CoreError("a Cargo manifest changed after the Explorer source fingerprint")
            package = tomllib.loads(data.decode()).get("package")
        except (OSError, ValueError) as error:
            raise CoreError("could not read a verified Cargo manifest for SCIP") from error
        if isinstance(package, dict) and isinstance(package.get("name"), str):
            names.add(package["name"])
    return sorted(names)


def _native_calls(
    connection: sqlite3.Connection,
    calls: list[Row],
    declarations: dict[str, str],
    locations: Row,
) -> tuple[list[Row], set[str]]:
    request: list[Row] = []
    paths: set[str] = set()
    for call in calls:
        call_id = as_text(call["id"], "native call ID")
        evidence_ids = as_text_list(call.get("evidence_ids"), "native call evidence")
        if len(evidence_ids) == 1:
            path, line = _location(locations, evidence_ids[0])
            paths.add(path)
        if call.get("status") == "resolved":
            # Reuse the existing canonical definition selection from the native projection.
            row = connection.execute(
                "SELECT target FROM relation WHERE id=?", ("relation:call:" + call_id,)
            ).fetchone()
            target = row[0] if row else None
            if isinstance(target, str) and target.startswith("definition:"):
                target = target.removeprefix("definition:")
                evidence = declarations.get(target)
                decl_path, decl_line = _location(locations, evidence) if evidence else (None, None)
                connection.execute(
                    """INSERT INTO call_resolution(
                        call_id, language, status, provenance, canonical_target_definition_id,
                        dispatch_kind, evidence_id, declaration_path, declaration_line)
                       VALUES (?, 'rust', 'local_resolved', 'ast_exact', ?, 'direct', ?, ?, ?)""",
                    (call_id, target, evidence, decl_path, decl_line),
                )
                continue
        if len(evidence_ids) == 1 and call.get("evidence_class") == "FACT":
            request.append(
                dict(
                    id=call_id,
                    path=path,
                    line=line,
                    module=call["source_module"],
                    expression=call["expression"],
                    macro_call=call.get("reason") == _MACRO,
                )
            )
        else:
            connection.execute(
                """INSERT INTO call_resolution(call_id, language, status, reason)
                   VALUES (?, 'rust', 'unresolved', 'no_scip_ref')""",
                (call_id,),
            )
    return request, paths


def _read_record(stream: BinaryIO, limit: int, field: str) -> Row | None:
    line = stream.readline(limit + 1)
    if not line:
        return None
    if len(line) > limit or not line.endswith(b"\n"):
        raise CoreError(f"invalid or oversized SCIP {field} record")
    try:
        return as_object(json.loads(line), field)
    except (UnicodeError, ValueError) as error:
        raise CoreError(f"invalid SCIP {field} record") from error


def _reference(row: Row, path: str, files: dict[str, str]) -> tuple[object, ...]:
    value = as_object(row.get("reference"), "SCIP reference")
    if value.get("path") != path or path not in files:
        raise CoreError("SCIP returned a reference outside the verified scan")
    coordinates = tuple(
        as_count(value.get(name), f"SCIP {name}")
        for name in ("start_line", "start_column", "end_line", "end_column")
    )
    if coordinates[:2] >= coordinates[2:]:
        raise CoreError("invalid SCIP reference range")
    return path, *coordinates


def _checked_columns(
    row: Row, path: str, declarations: dict[str, str], locations: Row, files: dict[str, str]
) -> tuple[object, ...]:
    status, provenance, reason = row.get("status"), row.get("provenance"), row.get("reason")
    declaration: tuple[object, ...] = (None,) * 5
    package: tuple[object, ...] = (None,) * 3
    reference: tuple[object, ...] = (None,) * 5
    if provenance == "scip_verified":
        reference = _reference(row, path, files)
    elif row.get("reference") is not None:
        raise CoreError("a SCIP reference must carry verified provenance")
    if status == "local_resolved" and provenance == "scip_verified" and reason is None:
        target = as_text(row.get("target_definition_id"), "SCIP target ID")
        dispatch = as_text(row.get("dispatch_kind"), "SCIP dispatch kind")
        evidence = as_text(row.get("evidence_id"), "SCIP declaration evidence")
        declaration_path = as_text(row.get("path"), "SCIP declaration path")
        line = as_count(row.get("line"), "SCIP declaration line")
        if (
            dispatch not in ("direct", "trait_dispatch")
            or declaration_path not in files
            or declarations.get(target) != evidence
            or (declaration_path, line) != _location(locations, evidence)
        ):
            raise CoreError("SCIP returned a declaration outside the verified scan")
        declaration = target, dispatch, evidence, declaration_path, line
    elif (
        status in ("external_std", "external_dep")
        and provenance == "scip_verified"
        and reason is None
    ):
        name = as_text(row.get("crate_name"), "SCIP crate name")
        version = row.get("crate_version")
        symbol = as_text(row.get("symbol_path"), "SCIP symbol path")
        if (name in _STDLIB) != (status == "external_std") or (
            version is not None and not isinstance(version, str)
        ):
            raise CoreError("invalid SCIP dependency identity")
        package = name, version, symbol
    elif status != "unresolved" or (reason, provenance) not in (
        ("macro_call", "ast_exact"),
        ("unmapped_scip_ref", "scip_verified"),
        ("no_scip_ref", None),
    ):
        raise CoreError("invalid SCIP resolution classification")
    return status, provenance, reason, *declaration, *package, *reference


def _write_rows(
    connection: sqlite3.Connection,
    output: BinaryIO,
    artifact: ScipIndex,
    digests: dict[str, str],
    calls: list[Row],
    declarations: dict[str, str],
    locations: Row,
) -> None:
    output.seek(0, 2)
    if output.tell() > _REPLY_LIMIT:
        raise CoreError("the SCIP evidence result exceeds the 64 MiB limit")
    output.seek(0)
    header = _read_record(output, _MANIFEST_LIMIT + _ROW_LIMIT, "header")
    if header is None or (header.get("index_sha256"), header.get("manifest_sha256")) != (
        artifact.index_sha256,
        artifact.manifest_sha256,
    ):
        raise CoreError("the SCIP worker read a different index or manifest")
    files = as_texts(header.get("source_files"), "SCIP verified source files")
    if any(len(digest) != 64 or digests.get(path) != digest for path, digest in files.items()):
        raise CoreError("the SCIP files differ from the Explorer source fingerprint")
    pending = {as_text(call["id"], "call ID"): as_text(call["path"], "call path") for call in calls}
    while (row := _read_record(output, _ROW_LIMIT, "binding")) is not None:
        call = as_text(row.get("call_id"), "SCIP call ID")
        path = pending.pop(call, None)
        if path is None:
            raise CoreError("unexpected or duplicate SCIP call ID")
        connection.execute(
            "INSERT INTO call_resolution VALUES (?, 'rust', ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (call, *_checked_columns(row, path, declarations, locations, files)),
        )
    if pending:
        raise CoreError("the SCIP worker omitted native call IDs")


def _store_resolution(
    connection: sqlite3.Connection,
    artifact: ScipIndex,
    binary: Path,
    root: Path,
    digests: dict[str, str],
    topology: Row,
) -> None:
    for statement in _SCHEMA[:2]:
        connection.execute(statement)
    calls, definitions, locations = _inputs(topology)
    declarations = {
        as_text(row["id"], "definition ID"): as_text(row["evidence_id"], "definition evidence")
        for row in definitions
    }
    pending, paths = _native_calls(connection, calls, declarations, locations)
    request = json.dumps(
        dict(calls=pending, definitions=definitions, local_packages=_packages(root, paths, digests))
    ).encode()
    if len(request) > _REQUEST_LIMIT:
        raise CoreError("the SCIP evidence request exceeds the 16 MiB limit")
    confirm(binary)
    worker, _ = collector_workers(binary)
    arguments: tuple[str, ...] = (str(root), str(artifact.path))
    if artifact.manifest_sha256 is not None:
        arguments += (str(artifact.manifest),)
    with tempfile.TemporaryFile(mode="w+b") as output:
        _, status = exchange(
            str(worker), "scip-evidence", request, arguments=arguments, output=output
        )
        if status:
            raise CoreError(f"the SCIP evidence worker failed (exit {status})")
        _write_rows(connection, output, artifact, digests, pending, declarations, locations)
    connection.execute(
        "INSERT INTO scip_artifact VALUES (?, ?)", (artifact.index_sha256, artifact.manifest_sha256)
    )
    connection.execute(_SCHEMA[2])
