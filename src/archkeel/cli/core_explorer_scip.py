# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Bind optional SCIP declarations to the verified Explorer frame."""

from __future__ import annotations

import hashlib
import json
import stat
from collections.abc import Iterator
from dataclasses import dataclass, replace
from pathlib import Path

from archkeel.explorer_store import SnapshotIdentity

from .core_binary import collector_workers, confirm
from .core_explorer_identity import _file_digest
from .core_json import CoreError, as_count, as_object, as_text, as_text_list, as_texts
from .native_scan import exchange

_INDEX_LIMIT = 64 << 20
_MANIFEST_LIMIT = 8 << 20
_REQUEST_LIMIT = 16 << 20
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
    """The exact index and manifest that bound one optional Explorer snapshot."""

    path: Path
    manifest: Path
    index_sha256: str
    manifest_sha256: str

    @classmethod
    def read(cls, requested: Path) -> ScipIndex:
        """Bind the regular artifact files without following a final symlink."""
        path = requested.parent.resolve() / requested.name
        manifest = path.with_name(path.name + ".manifest.json")
        return cls(
            path,
            manifest,
            _artifact_digest(path, _INDEX_LIMIT),
            _artifact_digest(manifest, _MANIFEST_LIMIT),
        )

    def bind(self, identity: SnapshotIdentity) -> SnapshotIdentity:
        """Keep an Explorer cache entry specific to these artifact bytes."""
        contract = json.dumps([identity.contract, "scip", self.index_sha256, self.manifest_sha256])
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
        for call in _rows(part.get("calls"), "calls"):
            if call.get("status") != "unresolved" or call.get("evidence_class") != "FACT":
                continue
            evidence = as_text_list(call.get("evidence_ids"), "call evidence")
            if len(evidence) == 1:
                path, line = _location(locations, evidence[0])
                calls.append(
                    dict(
                        id=call["id"],
                        path=path,
                        line=line,
                        module=call["source_module"],
                        expression=call["expression"],
                    )
                )
        for symbol in _rows(part.get("symbols"), "symbols"):
            if symbol.get("kind") not in ("function", "method") or not symbol.get("qualified_name"):
                continue
            evidence = as_text_list(symbol.get("evidence_ids"), "definition evidence")
            if len(evidence) == 1:
                definitions.append(
                    dict(id=symbol["id"], evidence_id=evidence[0], kind=symbol["kind"])
                )
    return calls, definitions, locations


def _bindings(
    reply: Row, calls: list[Row], definitions: list[Row], locations: Row, files: dict[str, str]
) -> dict[str, Row]:
    requested = {
        as_text(call["id"], "call ID"): as_text(call["path"], "call path") for call in calls
    }
    declarations = {as_text(row["id"], "definition ID"): row["evidence_id"] for row in definitions}
    matches: dict[str, Row] = {}
    entries = reply.get("bindings")
    if not isinstance(entries, list):
        raise CoreError("invalid SCIP binding result")
    for binding in _rows(entries, "bindings"):
        call_id = as_text(binding.get("call_id"), "SCIP call ID")
        target = as_text(binding.get("target_definition_id"), "SCIP target ID")
        evidence = as_text(binding.get("evidence_id"), "SCIP declaration evidence")
        line = as_count(binding.get("line"), "SCIP declaration line")
        path = as_text(binding.get("path"), "SCIP declaration path")
        if (
            requested.get(call_id) not in files
            or path not in files
            or call_id in matches
            or declarations.get(target) != evidence
            or (path, line) != _location(locations, evidence)
        ):
            raise CoreError("SCIP returned a declaration outside the verified scan")
        matches[call_id] = dict(target_definition_id=target, path=path, line=line)
    return matches


def enrich(
    artifact: ScipIndex, binary: Path, root: Path, digests: dict[str, str], topology: Row
) -> None:
    """Store only Rust-worker bindings that refer to this frame and fingerprint."""
    calls, definitions, locations = _inputs(topology)
    request = json.dumps(dict(calls=calls, definitions=definitions)).encode()
    if len(request) > _REQUEST_LIMIT:
        raise CoreError("the SCIP evidence request exceeds the 16 MiB limit")
    confirm(binary)
    worker, _ = collector_workers(binary)
    output, status = exchange(
        str(worker),
        "scip-evidence",
        request,
        arguments=(str(root), str(artifact.path), str(artifact.manifest)),
    )
    if status:
        raise CoreError(f"the SCIP evidence worker failed (exit {status})")
    reply = as_object(json.loads(output), "SCIP evidence result")
    if (reply.get("index_sha256"), reply.get("manifest_sha256")) != (
        artifact.index_sha256,
        artifact.manifest_sha256,
    ):
        raise CoreError("the SCIP worker read a different index or manifest")
    files = as_texts(reply.get("manifest_files"), "SCIP manifest files")
    if any(len(digest) != 64 or digests.get(path) != digest for path, digest in files.items()):
        raise CoreError("the SCIP manifest differs from the Explorer source fingerprint")
    bindings = _bindings(reply, calls, definitions, locations, files)
    topology["scip_bindings"] = bindings
    topology["scip"] = dict(
        provenance="scip",
        index_sha256=artifact.index_sha256,
        manifest_sha256=artifact.manifest_sha256,
        matched_calls=len(bindings),
        eligible_calls=len(calls),
    )
