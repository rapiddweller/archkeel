# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Compose the canonical architecture report of every analyzer profile."""

from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath
from typing import Literal

from archkeel.ir.codec import (
    ContractInputError,
    InsideContractMount,
    canonical_json_bytes,
    decode_json,
    load_inside_contract_tree,
    parse_observation,
)
from archkeel.ir.digest import package_digest
from archkeel.ir.facts import SourceFacts, dart_module_name
from archkeel.ir.facts_codec import RawRecord, classified
from archkeel.ir.identity import module_identity
from archkeel.ir.model import (
    SCHEMA_VERSION,
    ArchitectureContract,
    EvidenceClass,
    Observation,
    contract_relative_path,
    stable_id,
)
from archkeel.ir.profiles import PROFILES, Language, Profile

from .declarations import (
    load_contract,
    project_declarations,
    project_inside_declarations,
)
from .evaluation.evaluate import ScanResult, evaluate_source
from .ports import SourceCollector

OBSERVATION_VERSION = "0.70.0"

DEFAULT_CONTRACT = Path("docs/architecture/architecture-contract.json")


def _inside_levels(
    root: Path, contract_path: Path, contract: ArchitectureContract, root_digest: str
) -> tuple[
    list[RawRecord],
    str,
    list[InsideContractMount],
    list[RawRecord],
]:
    """Load and project every explicitly mounted inside contract (AD-34).

    A missing or invalid nested contract is an UNKNOWN in the observation, not an empty level.
    """
    records: list[RawRecord] = []
    failures: list[RawRecord] = []
    repository = root.resolve()

    def read_inside(path: str) -> tuple[bytes, str]:
        relative = contract_relative_path(path)
        if relative is None:
            raise ValueError("unsafe repository path")
        target = (repository / relative).resolve()
        if not target.is_relative_to(repository) or not target.is_file():
            raise ValueError("file is missing or outside the repository")
        return target.read_bytes(), target.relative_to(repository).as_posix()

    tree = load_inside_contract_tree(
        contract_path.relative_to(repository).as_posix(),
        contract,
        root_digest,
        contract_path.resolve().relative_to(repository).as_posix(),
        read_inside,
    )
    for issue in tree.issues:
        if issue.input_error is not None:
            raise ContractInputError(
                f"{issue.pointer}{issue.input_error.pointer}",
                issue.input_error.subject,
                str(issue.input_error),
            )
        record = classified(
            item_id=stable_id("UNKNOWN-INSIDE-CONTRACT", issue.parent_id, issue.path),
            evidence_class=EvidenceClass.UNKNOWN,
            area="analysis_coverage",
            kind="inside_contract_incomplete",
            title=f"{issue.parent.label} inside contract cannot be evaluated: {issue.reason}",
            subjects=[issue.parent_id, issue.path],
            data={"parent_id": issue.parent_id, "path": issue.path, "reason": issue.reason},
        )
        failures.append(record)
    for mount in tree.mounts:
        records.extend(project_inside_declarations(mount.parent_id, mount.contract, mount.path))
    return records, tree.digest, list(tree.mounts), failures


def _contract_source(
    source_root: Path, contract_root: Path | None, contract_path: Path | None
) -> tuple[Path, Path]:
    """Return the root that declared paths are relative to, and the contract file itself."""
    declarations_root = (contract_root or source_root).resolve()
    contract_file = contract_path or declarations_root / DEFAULT_CONTRACT
    if not contract_file.is_absolute():
        contract_file = declarations_root / contract_file
    return declarations_root, contract_file


def _metric(
    kind: str,
    title: str,
    value: int | float | str | None,
    tab: str,
    *,
    fact_ids: list[str] | None = None,
) -> RawRecord:
    return classified(
        item_id=stable_id("METRIC", kind),
        evidence_class=EvidenceClass.FACT,
        area="overview",
        kind=kind,
        title=title,
        fact_ids=fact_ids,
        data={"value": value, "tab": tab},
    )


def _metrics(scan: ScanResult, contract: ArchitectureContract, profile: Profile) -> list[RawRecord]:
    dependency_violations = [
        item for item in scan.violations if item["kind"] == "forbidden_dependency"
    ]
    private_crossings = [
        item
        for item in scan.imports
        if item["data"]["symbol"]
        and item["data"]["symbol"].startswith("_")
        and item["data"]["source_package"] != item["data"]["target_package"]
    ]
    private_attribute_limits = [
        item for item in scan.unknowns if item["kind"] == "private_attribute_access_limit"
    ]
    package_cycles = [item for item in scan.cycles if item["data"]["level"] == "package"]
    module_cycles = [item for item in scan.cycles if item["data"]["level"] == "module"]
    rollup_only = [item for item in package_cycles if not item["data"]["backed_by"]]
    unresolved_calls = [item for item in scan.calls if item["data"]["status"] == "unresolved"]
    resolved_calls = [item for item in scan.calls if item["data"]["status"] == "resolved"]
    evidence_by_id = {item["id"]: item for item in scan.evidence}
    violating_import_sites = {
        (
            evidence_by_id[evidence_id]["file"],
            evidence_by_id[evidence_id]["line"],
            evidence_by_id[evidence_id]["end_line"],
            evidence_by_id[evidence_id]["column"],
        )
        for item in dependency_violations
        for evidence_id in item["evidence_ids"]
        if evidence_id in evidence_by_id
    }
    affected_violation_modules = {item["data"]["source_module"] for item in dependency_violations}
    package_by_module = {
        item["data"]["qualified_name"]: item["data"]["package"]
        for item in scan.modules
        if item["data"].get("qualified_name") and item["data"].get("package")
    }
    imports_by_pair: dict[tuple[str, str], list[RawRecord]] = {}
    for item in scan.imports:
        pair = (item["data"]["source_module"], item["data"]["target_module"])
        imports_by_pair.setdefault(pair, []).append(item)
    forbidden_package_edges: set[tuple[str, str]] = set()
    for violation in dependency_violations:
        pair = (
            violation["data"]["source_module"],
            violation["data"]["target_module"],
        )
        matching_imports = imports_by_pair.get(pair, ())
        for item in matching_imports:
            source_package = package_by_module.get(pair[0], item["data"]["source_package"])
            target_package = package_by_module.get(pair[1], item["data"]["target_package"])
            if source_package and target_package:
                forbidden_package_edges.add((source_package, target_package))
    violation_fact_ids = sorted(
        {fact_id for item in scan.violations for fact_id in item["fact_ids"]}
    )
    interface_usage = [
        (item, source, target)
        for item in scan.imports
        if (source := contract.component_for(item["data"]["source_module"])) is not None
        and (target := contract.component_for(item["data"]["target_module"])) is not None
        and source != target
    ]
    interface_surface = {
        (
            target.label,
            ".".join(filter(None, (item["data"]["target_module"], item["data"]["symbol"]))),
        )
        for item, _, target in interface_usage
    }
    return sorted(
        [
            _metric(
                "source_files",
                "Source files",
                scan.coverage["files_discovered"],
                "coverage",
                fact_ids=[item["id"] for item in scan.modules],
            ),
            _metric(
                "packages",
                "Packages",
                len(scan.packages),
                "package",
                fact_ids=[item["id"] for item in scan.packages],
            ),
            _metric(
                "modules",
                "Modules",
                len(scan.modules),
                "module",
                fact_ids=[item["id"] for item in scan.modules],
            ),
            _metric(
                "symbols",
                "Symbols",
                None if "symbols" in profile.absent_sections else len(scan.symbols),
                "components",
                fact_ids=(
                    [item["id"] for item in scan.symbols]
                    if "symbols" not in profile.absent_sections
                    else None
                ),
            ),
            _metric(
                "package_cycles",
                "Package cycles",
                len(package_cycles),
                "cycles",
                fact_ids=[item["id"] for item in package_cycles],
            ),
            # AD-98: a package SCC no module cycle crosses is the two-segment roll-up's.
            _metric(
                "rollup_only_package_cycles",
                "Package cycles no module cycle crosses",
                len(rollup_only),
                "cycles",
                fact_ids=[item["id"] for item in rollup_only],
            ),
            _metric(
                "module_cycles",
                "Module cycles",
                len(module_cycles),
                "cycles",
                fact_ids=[item["id"] for item in module_cycles],
            ),
            _metric(
                "violations",
                "Forbidden symbol crossings",
                len(scan.violations),
                "violations",
                fact_ids=violation_fact_ids,
            ),
            _metric(
                "violating_import_sites",
                "Violating import sites",
                len(violating_import_sites),
                "violations",
                fact_ids=violation_fact_ids,
            ),
            _metric(
                "affected_violation_modules",
                "Affected source modules",
                len(affected_violation_modules),
                "violations",
                fact_ids=[
                    item["id"]
                    for item in scan.modules
                    if item["data"]["qualified_name"] in affected_violation_modules
                ],
            ),
            _metric(
                "forbidden_package_edges",
                "Forbidden package edges",
                len(forbidden_package_edges),
                "violations",
                fact_ids=[
                    item["id"]
                    for item in scan.dependency_edges
                    if item["data"]["level"] == "package"
                    and (item["data"]["source"], item["data"]["target"]) in forbidden_package_edges
                ],
            ),
            _metric(
                "private_crossings",
                "Confirmed private symbol crossings",
                None if "private_crossings" in profile.unmeasured else len(private_crossings),
                "api",
                fact_ids=(
                    [item["id"] for item in private_crossings]
                    if "private_crossings" not in profile.unmeasured
                    else None
                ),
            ),
            _metric(
                "untyped_private_accesses",
                "Private attribute accesses through untyped or Any parameters",
                None
                if "untyped_private_accesses" in profile.unmeasured
                else len(private_attribute_limits),
                "api",
            ),
            _metric(
                "typing_signals",
                "Typing & dynamic signals",
                None
                if "typing_signals" in profile.absent_sections
                or "typing_positions" in profile.unmeasured
                else len(scan.typing_signals),
                "types",
                fact_ids=(
                    [item["id"] for item in scan.typing_signals]
                    if "typing_signals" not in profile.absent_sections
                    and "typing_positions" not in profile.unmeasured
                    else None
                ),
            ),
            _metric(
                "unresolved_calls",
                "Unresolved calls",
                None
                if "calls_unresolved" in profile.unmeasured
                else scan.coverage["calls_unresolved"],
                "calls",
                fact_ids=(
                    [item["id"] for item in unresolved_calls]
                    if "calls_unresolved" not in profile.unmeasured
                    else None
                ),
            ),
            _metric(
                "ast_coverage",
                "AST coverage",
                f"{scan.coverage['ast_coverage_percent']}%",
                "coverage",
                fact_ids=[item["id"] for item in scan.modules],
            ),
            _metric(
                "call_resolution",
                "Uniquely resolved calls",
                None
                if "calls_unresolved" in profile.unmeasured
                else f"{scan.coverage['call_resolution_percent']}%",
                "calls",
                fact_ids=(
                    [item["id"] for item in resolved_calls]
                    if "calls_unresolved" not in profile.unmeasured
                    else None
                ),
            ),
            _metric(
                "interface_surface",
                "Interface surface",
                len(interface_surface),
                "api",
                fact_ids=[item["id"] for item, _, _ in interface_usage],
            ),
        ],
        key=lambda item: item["id"],
    )


def _dart_target_names(
    records: list[RawRecord], scan: ScanResult, roots: tuple[str, ...], namespace: str
) -> dict[str, str]:
    paths_by_name: dict[str, set[str]] = {}
    names: dict[str, str] = {}
    for record in scan.modules:
        name, path = record["data"].get("qualified_name"), record["data"].get("file")
        if isinstance(name, str) and isinstance(path, str):
            paths_by_name.setdefault(name, set()).add(path)
    for record in records:
        path = record["data"].get("path")
        if record["kind"] != "module_target" or not isinstance(path, str):
            continue
        name = _declared_module_name(path, roots, namespace, "dart")
        if name is not None:
            names[record["id"]] = name
            paths_by_name.setdefault(name, set()).add(path)
    for record in records:
        name = names.get(record["id"])
        if name is None or len(paths_by_name[name]) == 1:
            continue
        paths = sorted(paths_by_name[name])
        del names[record["id"]]
        scan.unknowns.append(
            classified(
                item_id=stable_id("UNKNOWN-MODULE-TARGET", record["id"]),
                evidence_class=EvidenceClass.UNKNOWN,
                area="module_targets",
                kind="module_target_identity_ambiguity",
                title=(
                    f"different source paths share Dart module identity {name}: {', '.join(paths)}"
                ),
                subjects=paths,
                provenance=record["provenance"],
                data={"qualified_name": name, "paths": paths},
            )
        )
    return names


def _declaration_records(
    contract: ArchitectureContract,
    scan: ScanResult,
    inside_records: list[RawRecord],
    contract_path: str,
    module_scope: tuple[tuple[str, ...], str],
    language: Language,
) -> list[RawRecord]:
    """`project_declarations` needs `scan`'s own `symbols`/`imports`/`modules` to resolve
    `declared_public_api`'s `types` (AD-70); kept out of `analyze_snapshot`'s own body only to
    keep that call a single line there.
    """
    records = [
        *project_declarations(
            contract,
            scan.symbols,
            scan.imports,
            scan.modules,
            contract_path,
            unknowns=scan.unknowns,
            type_shapes=scan.type_shapes,
            measured_types="symbols" not in PROFILES[language].absent_sections,
        ),
        *inside_records,
    ]
    roots, namespace = module_scope
    dart_names = _dart_target_names(records, scan, roots, namespace) if language == "dart" else {}
    for record in records:
        data = record["data"]
        if record["kind"] != "module_target" or "path" not in data:
            continue
        path = data["path"]
        if not isinstance(path, str):
            continue
        qualified_name = (
            dart_names.get(record["id"])
            if language == "dart"
            else _declared_module_name(path, roots, namespace, language)
        )
        if qualified_name is not None:
            record["data"] = {**record["data"], "qualified_name": qualified_name}
    scan.unknowns = sorted(scan.unknowns, key=lambda item: item["id"])
    return records


def _declared_module_name(
    path: str, roots: tuple[str, ...], namespace: str, language: Language = "python"
) -> str | None:
    if language == "dart":
        source_path = PurePosixPath(path)
        if source_path.suffix != ".dart":
            return None
        names = [
            dart_module_name(source_path.relative_to(PurePosixPath(root)).as_posix())
            for root in roots
            if source_path.is_relative_to(PurePosixPath(root))
        ]
        return f"{namespace}.{names[0]}" if len(names) == 1 and names[0] is not None else None
    if language == "typescript":
        source_path = PurePosixPath(path)
        if not any(source_path.is_relative_to(PurePosixPath(root)) for root in roots):
            return None
        if PurePosixPath(path).suffix not in {
            ".ts",
            ".tsx",
            ".mts",
            ".cts",
            ".js",
            ".jsx",
            ".mjs",
            ".cjs",
        }:
            return None
        try:
            return module_identity(namespace, path)
        except ValueError:
            return None
    target = Path(path).parts
    namespace_parts = tuple(namespace.split("."))
    anchors: list[tuple[str, ...]] = []
    for root in roots:
        root_parts = Path(root).parts
        if target[: len(root_parts)] != root_parts:
            continue
        relative_file = target[len(root_parts) :]
        if not relative_file:
            continue
        target_filename = relative_file[-1]
        if target_filename[-3:] != ".py":
            continue
        relative = (*relative_file[:-1], target_filename[:-3])
        if root_parts[-len(namespace_parts) :] == namespace_parts:
            anchor = len(root_parts) - len(namespace_parts)
            parts = (*namespace_parts, *relative)
        elif relative[: len(namespace_parts)] == namespace_parts:
            anchor = len(root_parts)
            parts = relative
        else:
            continue
        if any(
            target[index : index + len(namespace_parts)] == namespace_parts
            for index in range(anchor)
        ):
            continue
        if parts and parts[-1] == "__init__":
            parts = parts[:-1]
        if parts:
            anchors.append(parts)
    return ".".join(anchors[0]) if len(anchors) == 1 else None


def _add_git_failure(scan: ScanResult, git_head: str, dirty: bool | str) -> None:
    """Git metadata the run could not record makes the scan incomplete, never silently so."""
    git_failure = classified(
        item_id="UNKNOWN-GIT-REVISION",
        evidence_class=EvidenceClass.UNKNOWN,
        area="analysis_coverage",
        kind="git_metadata_failure",
        title="Git revision metadata could not be recorded",
        subjects=["repository"],
        data={"git_head": git_head, "dirty": dirty},
    )
    scan.unknowns = sorted([*scan.unknowns, git_failure], key=lambda item: item["id"])
    scan.coverage["failures"] = sorted(
        [*scan.coverage["failures"], git_failure], key=lambda item: item["id"]
    )
    scan.coverage["status"] = "FAIL"


def _record_inside_failures(scan: ScanResult, failures: list[RawRecord]) -> None:
    """Carry unreadable or out-of-scope nested contracts as scan UNKNOWNs and coverage failures."""
    if not failures:
        return
    scan.unknowns = sorted([*scan.unknowns, *failures], key=lambda item: item["id"])
    scan.coverage["failures"] = sorted(
        [*scan.coverage["failures"], *failures], key=lambda item: item["id"]
    )
    scan.coverage["status"] = "FAIL"
    scan.coverage["rules"] = "FAIL"


def assemble_observation(
    facts: SourceFacts,
    *,
    contract_root: Path,
    contract_path: Path | None = None,
    roots: tuple[str, ...] = ("src",),
    namespace: str = "src",
    language: Language = "python",
) -> tuple[Observation, int]:
    """Analyze explicit source bytes; keep the model open for the canonical codec boundary."""
    git_head, dirty = facts.source.git_head, facts.source.dirty
    declarations_root, contract_file = _contract_source(contract_root, contract_root, contract_path)
    contract_reference = contract_file.relative_to(declarations_root).as_posix()
    contract, contract_digest = load_contract(contract_file)
    inside_records, full_contract_digest, inside_contracts, inside_failures = _inside_levels(
        declarations_root, contract_file, contract, contract_digest
    )
    profile = PROFILES[language]
    scan = evaluate_source(
        facts,
        contract,
        roots=roots,
        namespace=namespace,
        inside_contracts=inside_contracts,
    )
    _record_inside_failures(scan, inside_failures)
    if git_head == "unknown" or dirty == "unknown":
        _add_git_failure(scan, git_head, dirty)
    scope = roots, namespace
    declarations = _declaration_records(
        contract, scan, inside_records, contract_reference, scope, language
    )
    model: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "analyzer": {
            "name": profile.analyzer,
            "version": OBSERVATION_VERSION,
            "code_digest": hashlib.sha256(
                f"{package_digest()}\0{facts.adapter.name}\0{facts.adapter.code_digest}".encode()
            ).hexdigest(),
        },
        "source": {
            "git_head": git_head,
            "dirty": dirty,
            "source_digest": scan.source_digest,
            "scope": list(facts.source.scope),
        },
        "contract": {
            "schema_version": contract.schema_version,
            "digest": full_contract_digest,
            "path": contract_reference,
        },
        "coverage": scan.coverage,
        "metrics": _metrics(scan, contract, profile),
        "declarations": declarations,
        "scope_observations": scan.scope_observations,
        "packages": scan.packages,
        "modules": scan.modules,
        "symbols": scan.symbols,
        "imports": scan.imports,
        "dependency_edges": scan.dependency_edges,
        "transitive_paths": scan.transitive_paths,
        "path_observations": scan.path_observations,
        "cycles": scan.cycles,
        "calls": scan.calls,
        "references": scan.references,
        "bindings": scan.bindings,
        "typing_signals": scan.typing_signals,
        "constructs": scan.constructs,
        "contexts": scan.contexts,
        "context_evidence": scan.context_evidence,
        "violations": scan.violations,
        "unknowns": scan.unknowns,
        "evidence": scan.evidence,
    }
    model["runtime"] = {
        "name": facts.runtime.name,
        "version": facts.runtime.version,
        "required": facts.runtime.required,
    }
    if language == "python" and facts.runtime.name == "python":
        model["python_version"] = facts.runtime.version
    if language != "python" or facts.adapter.name != profile.analyzer:
        model["producer"] = {
            "name": facts.adapter.name,
            "version": facts.adapter.version,
            "code_digest": facts.adapter.code_digest,
        }
    # AD-97: a signal the profile never produces is null, so a claim on it reads UNKNOWN.
    for section in profile.absent_sections:
        model[section] = None
    normalized = decode_json(canonical_json_bytes(model))
    if not isinstance(normalized, dict):
        raise ValueError("assembled observation must be an object")
    return parse_observation(normalized), 0 if scan.coverage["status"] == "PASS" else 2


def analyze_source_snapshot(
    collector: SourceCollector,
    source_root: Path,
    *,
    git_head: str,
    dirty: bool | Literal["unknown"],
    contract_root: Path | None = None,
    contract_path: Path | None = None,
    roots: tuple[str, ...] = ("src",),
    namespace: str = "src",
    language: Language = "python",
) -> tuple[Observation, int]:
    """Collect and assemble one snapshot for demo and audit callers."""
    from archkeel.ir.protocol import (
        CollectionError,
        CollectionRequest,
        DartSettings,
        PythonSettings,
        ResolverSettings,
        SnapshotInput,
        SourceScope,
        TypeScriptSettings,
    )

    if dirty != "unknown" and not isinstance(dirty, bool):
        raise ValueError("dirty must be a boolean or unknown")
    resolver: ResolverSettings = (
        TypeScriptSettings()
        if language == "typescript"
        else DartSettings()
        if language == "dart"
        else PythonSettings()
    )
    request = CollectionRequest(
        SnapshotInput(str(source_root.resolve()), git_head, dirty),
        SourceScope(roots, namespace),
        resolver,
    )
    facts = collector.collect(request)
    if isinstance(facts, CollectionError):
        raise ValueError(facts.message)
    return assemble_observation(
        facts,
        contract_root=contract_root or source_root,
        contract_path=contract_path,
        roots=roots,
        namespace=namespace,
        language=language,
    )
