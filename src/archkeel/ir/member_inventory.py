# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Bind complete native member inventories to one eligible collected snapshot."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import asdict
from pathlib import PurePosixPath

from archkeel.ir.facts import (
    SOURCE_RESOLUTION_GAP_KIND,
    InventoryStatus,
    ResolutionInput,
    ResolutionRole,
    member_inventories,
)
from archkeel.ir.facts import RuntimeRequirementState as _RuntimeRequirementState
from archkeel.ir.identity_memo import IdentityMemo
from archkeel.ir.model import (
    TARGET_GRAPH_RECORD_KINDS,
    EvidenceClass,
    Observation,
    RawJson,
    Record,
    RecordData,
    Verdict,
    stable_id,
)
from archkeel.ir.source_values import record_array, vocabulary_text

MEMBER_INVENTORY_PROOF = "member_inventory_proof"
_INVENTORY_SOURCE_SECTIONS = (
    "modules",
    "packages",
    "symbols",
    "imports",
    "references",
    "calls",
    "bindings",
    "typing_signals",
    "constructs",
)


def _inventory_digest(value: RawJson) -> str:
    payload: str = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _inventory_binding(model: Observation) -> str:
    return _inventory_digest(
        {
            "analyzer": asdict(model.analyzer),
            "producer": asdict(model.producer) if model.producer else None,
            "source": asdict(model.source),
            "contract": asdict(model.contract),
            "runtime": asdict(model.runtime) if model.runtime else None,
            "coverage": asdict(model.coverage),
            "evidence": [asdict(e) for e in model.evidence],
            "declarations": [
                asdict(r)
                for r in model.records("declarations") or ()
                if r.kind not in TARGET_GRAPH_RECORD_KINDS
            ],
            "sections": {
                name: [asdict(r) for r in model.records(name) or ()]
                for name in _INVENTORY_SOURCE_SECTIONS
            },
        }
    )


def _inventory_selected_inputs(model: Observation, inputs: tuple[RecordData, ...]) -> set[str]:
    if model.analyzer.name not in {"archkeel-dart-analyzer", "archkeel-typescript-imports"}:
        return set()
    runtime = model.runtime
    version: str = runtime.version if runtime is not None else ""
    if (
        runtime is None
        or runtime.name != "python"
        or runtime.required != ">=3.11"
        or runtime.requirement_state != _RuntimeRequirementState.DECLARED
        or re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version) is None
        or tuple(int(v) for v in version.split(".")) < (3, 11, 0)
    ):
        return set()
    if model.producer is None or model.producer.name != model.analyzer.name:
        return set()
    if any(
        re.fullmatch(r"[0-9a-f]{64}", value) is None
        for value in (
            model.analyzer.code_digest,
            model.producer.code_digest,
            model.contract.digest,
            model.source.source_digest,
        )
    ):
        return set()
    rows: list[dict[str, str]] = []
    for item in inputs:
        path, digest, role = item.get("path"), item.get("digest"), item.get("role")
        relative: PurePosixPath = PurePosixPath(str(path))
        if (
            set(dict(item.entries)) != {"path", "digest", "role"}
            or not isinstance(path, str)
            or not path
            or path[:1] == "/"
            or ".." in relative.parts
            or "\\" in path
            or ":" in path
            or not isinstance(digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", digest) is None
            or not isinstance(role, str)
            or role not in {"selected", "resolution"}
        ):
            return set()
        rows.append({"path": path, "digest": digest, "role": role})
    if len({row["path"] for row in rows}) != len(rows):
        return set()
    listing: str = (
        "".join(json.dumps(row, separators=(",", ":"), ensure_ascii=False) for row in rows)
        if model.analyzer.name == "archkeel-dart-analyzer"
        else json.dumps(rows, separators=(",", ":"), ensure_ascii=False)
    )
    selected = {row["path"] for row in rows if row["role"] == "selected"}
    coverage = model.coverage
    if (
        hashlib.sha256(listing.encode()).hexdigest() != model.source.source_digest
        or not selected
        or coverage.status != Verdict.FAIL
        or coverage.rules != Verdict.PASS
        or not coverage.failures
        or coverage.files_discovered != len(selected)
        or coverage.files_read != len(selected)
        or coverage.files_parsed != len(selected)
    ):
        return set()
    return selected


def _inventory_libraries(model: Observation, selected: set[str]) -> dict[str, set[str]]:
    libraries: dict[str, set[str]] = {}
    for module_record in model.records("modules") or ():
        name, path = module_record.data.get("qualified_name"), module_record.data.get("file")
        if not isinstance(name, str) or not isinstance(path, str) or path not in selected:
            return {}
        if name in libraries:
            return {}
        libraries[name] = {path}
    evidence = {e.id: e for e in model.evidence}
    for record in model.records("symbols") or ():
        module = record.data.get("module")
        if not isinstance(module, str) or module not in libraries or not record.evidence_ids:
            return {}
        paths = {evidence[key].file for key in record.evidence_ids if key in evidence}
        if len(paths) != 1 or not paths <= selected:
            return {}
        libraries[module] |= paths
    return libraries


def _inventory_gap_files(
    model: Observation, selected: set[str], libraries: dict[str, set[str]]
) -> set[str] | None:
    evidence = {e.id: e for e in model.evidence}
    paths: set[str] = set()
    for gap in model.coverage.failures:
        keys = set(dict(gap.data.entries))
        if (
            gap.kind != SOURCE_RESOLUTION_GAP_KIND
            or gap.evidence_class != EvidenceClass.UNKNOWN
            or gap.area not in {"source", "analysis_coverage"}
            or not gap.evidence_ids
            or gap.rule_ids
            or keys
            - {
                "file",
                "line",
                "message",
                "module",
                "source_module",
                "reason",
                "resolution_dimension",
            }
        ):
            return None
        sites = [evidence.get(key) for key in gap.evidence_ids]
        if any(e is None or e.file not in selected or e.line <= 0 or not e.excerpt for e in sites):
            return None
        files = {e.file for e in sites if e is not None}
        modules = {name for name, owned in libraries.items() if files <= owned}
        if len(modules) != 1:
            return None
        file = gap.data.get("file")
        module, source_module = gap.data.get("module"), gap.data.get("source_module")
        reasons = [gap.data.get(key) for key in ("reason", "message") if key in keys]
        if not reasons:
            return None
        for value in reasons:
            if not isinstance(value, str):
                return None
            reason: str = value
            if not reason.strip():
                return None
        if file is None and module is None and source_module is None:
            return None
        if file is not None and (
            file not in files
            or type(gap.data.get("line")) is not int
            or gap.data.get("line") not in {e.line for e in sites if e}
        ):
            return None
        if any(value is not None and value not in modules for value in (module, source_module)):
            return None
        allowed_subjects = modules | {
            f"{e.file}:{e.line}" for e in sites if e is not None and e.file == file
        }
        if not gap.subjects or not set(gap.subjects) <= allowed_subjects:
            return None
        if gap.data.get("resolution_dimension") not in {None, "imports", "signature"}:
            return None
        paths.update(files)
    return paths


def _inventory_owners(model: Observation, selected: set[str]) -> tuple[str, ...]:
    libraries = _inventory_libraries(model, selected)
    gaps = _inventory_gap_files(model, selected, libraries)
    if not libraries or gaps is None:
        return ()
    symbols = model.records("symbols") or ()
    names = Counter(item.data.get("qualified_name") for item in symbols)
    return tuple(
        sorted(
            item.id
            for item in symbols
            if item.kind == "class"
            and not item.data.get("definition_contexts")
            and names[item.data.get("qualified_name")] == 1
            and isinstance((module := item.data.get("module")), str)
            and module in libraries
            and not libraries[module] & gaps
            and any(
                inv.status == InventoryStatus.COMPLETE
                for inv in member_inventories(item.data.get("member_inventories"))
            )
        )
    )


def member_inventory_proof(
    model: Observation, inputs: tuple[ResolutionInput, ...]
) -> Record | None:
    """Bind complete native direct inventories to one eligible collected snapshot."""
    rows = tuple(
        RecordData((("digest", item.digest), ("path", item.path), ("role", item.role)))
        for item in inputs
    )
    selected = _inventory_selected_inputs(model, rows)
    owners = _inventory_owners(model, selected) if selected else ()
    if not owners:
        return None
    binding = _inventory_binding(model)
    evidence = tuple(
        sorted(
            {
                e
                for item in model.records("symbols") or ()
                if item.id in owners
                for e in item.evidence_ids
            }
        )
    )
    return Record(
        stable_id("MEMBER-INVENTORY", binding),
        EvidenceClass.FACT,
        "source",
        MEMBER_INVENTORY_PROOF,
        "Direct native member inventories have complete local source",
        (),
        evidence,
        (),
        owners,
        (),
        RecordData((("binding", binding), ("inputs", rows), ("schema_version", "1.0.0"))),
    )


_REPLAYED: IdentityMemo[Observation, Record | None] = IdentityMemo()


def validated_member_inventory_proof(model: Observation) -> Record | None:
    """Replay the bound local source proof once for this observation object.

    A saved or changed observation is another object, so it replays again (AD-229).
    """
    return _REPLAYED.get(model, "proof", lambda: _replay_member_inventory_proof(model))


def _replay_member_inventory_proof(model: Observation) -> Record | None:
    """Replay the bound local source proof; absent or changed evidence stays unknown."""
    proofs = [
        r for r in model.records("scope_observations") or () if r.kind == MEMBER_INVENTORY_PROOF
    ]
    if len(proofs) != 1:
        return None
    proof = proofs[0]
    try:
        rows = record_array(proof.data.get("inputs"))
        selected = _inventory_selected_inputs(model, rows)
        expected = (
            member_inventory_proof(
                model,
                tuple(
                    ResolutionInput(
                        str(row.get("path")),
                        str(row.get("digest")),
                        ResolutionRole(vocabulary_text(row.get("role"))),
                    )
                    for row in rows
                ),
            )
            if selected
            else None
        )
        return proof if proof == expected else None
    except (TypeError, ValueError):
        return None
