# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Compose the canonical architecture report of every analyzer profile."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path
from typing import Any

from archkeel.ir.codec import ContractVersionError
from archkeel.ir.model import (
    SCHEMA_VERSION,
    ArchitectureContract,
    EvidenceClass,
    contract_relative_path,
    stable_id,
)
from archkeel.ir.profiles import PROFILES, Language

from .contract import (
    ContractError,
    load_contract,
    project_declarations,
    project_inside_declarations,
)
from .dart_scanner import scan_dart_repository
from .records import ANALYZER_VERSION, RawRecord, analyzer_code_digest, classified
from .scanner import ScanResult, scan_repository
from .violations import requires_violations

DEFAULT_CONTRACT = Path("docs/architecture/architecture-contract.json")


def _owned_rules(parent: str, inner: ArchitectureContract) -> ArchitectureContract:
    """Rename the inside's rules under the component holding them, once, on the way in (AD-36).

    Record ids are one namespace across both levels. Renaming here means everything downstream
    - the projected declaration, the violation and the id that violation is filed under - is
    built from the name it will be read by, instead of being corrected afterwards.
    """
    return replace(
        inner, rules=tuple(replace(rule, id=f"{parent}:{rule.id}") for rule in inner.rules)
    )


def _inside_levels(
    root: Path, contract: ArchitectureContract
) -> tuple[list[RawRecord], list[str], list[ArchitectureContract]]:
    """Load each declared inside contract, project it, and collect its digest (AD-34).

    A path that leaves the repository, a missing file and an unreadable contract are skipped
    rather than reported: `validate` owns that verdict and emits `contract.invalid`, so an
    observation carries a whole level or none of it.
    """
    records: list[RawRecord] = []
    digests: list[str] = []
    contracts: list[ArchitectureContract] = []
    for component in contract.components:
        if component.inside is None:
            continue
        relative = contract_relative_path(component.inside)
        if relative is None:
            continue
        target = (root / relative).resolve()
        if not target.is_relative_to(root) or not target.is_file():
            continue
        try:
            inner, digest = load_contract(target)
        except (ContractError, ContractVersionError):
            continue
        owned = _owned_rules(component.label, inner)
        records.extend(project_inside_declarations(component.label, owned))
        digests.append(digest)
        contracts.append(owned)
    return records, digests, contracts


def _contract_tree_digest(digest: str, inside_digests: list[str]) -> str:
    """Fold the inside contracts into the contract digest (AD-34).

    Comparability hangs on this value: unfolded, an edit to a level's own contract would change
    the picture while `delta` still called two observations comparable.
    """
    if not inside_digests:
        return digest
    return hashlib.sha256("".join([digest, *inside_digests]).encode()).hexdigest()


def _add_inside_violations(scan: ScanResult, contracts: list[ArchitectureContract]) -> None:
    """Evaluate each inside contract's rules against the imports already collected (AD-34).

    The same rule code as the level above. It reads finished import records, so a second level
    costs no second scan, and its verdict reaches both the view and the exit code through the
    records every other verdict travels in.
    """
    for inner in contracts:
        scan.violations.extend(requires_violations(scan.imports, inner))
    scan.violations.sort(key=lambda item: item["id"])


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
    value: int | float | str,
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


def _metrics(scan: ScanResult, contract: ArchitectureContract) -> list[RawRecord]:
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
    forbidden_package_edges = {
        (
            ".".join(item["data"]["source_module"].split(".")[:2]),
            ".".join(item["data"]["target_module"].split(".")[:2]),
        )
        for item in dependency_violations
    }
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
                len(scan.symbols),
                "components",
                fact_ids=[item["id"] for item in scan.symbols],
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
                len(private_crossings),
                "api",
                fact_ids=[item["id"] for item in private_crossings],
            ),
            _metric(
                "untyped_private_accesses",
                "Private attribute accesses through untyped or Any parameters",
                len(private_attribute_limits),
                "api",
            ),
            _metric(
                "typing_signals",
                "Typing & dynamic signals",
                len(scan.typing_signals),
                "types",
                fact_ids=[item["id"] for item in scan.typing_signals],
            ),
            _metric(
                "unresolved_calls",
                "Unresolved calls",
                scan.coverage["calls_unresolved"],
                "calls",
                fact_ids=[item["id"] for item in unresolved_calls],
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
                f"{scan.coverage['call_resolution_percent']}%",
                "calls",
                fact_ids=[item["id"] for item in resolved_calls],
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


def _declaration_records(
    contract: ArchitectureContract,
    scan: ScanResult,
    inside_records: list[RawRecord],
    contract_path: str,
) -> list[RawRecord]:
    """`project_declarations` needs `scan`'s own `symbols`/`imports`/`modules` to resolve
    `declared_public_api`'s `types` (AD-70); kept out of `analyze_snapshot`'s own body only to
    keep that call a single line there.
    """
    return [
        *project_declarations(contract, scan.symbols, scan.imports, scan.modules, contract_path),
        *inside_records,
    ]


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


def analyze_snapshot(
    source_root: Path,
    *,
    git_head: str,
    dirty: bool | str,
    contract_root: Path | None = None,
    contract_path: Path | None = None,
    source_paths: list[Path] | tuple[Path, ...] | None = None,
    roots: tuple[str, ...] = ("src",),
    namespace: str = "src",
    language: Language = "python",
) -> tuple[dict[str, Any], int]:
    """Analyze explicit source bytes and metadata without consulting Git."""
    source_root = source_root.resolve()
    declarations_root, contract_file = _contract_source(source_root, contract_root, contract_path)
    contract_reference = contract_file.relative_to(declarations_root).as_posix()
    contract, contract_digest = load_contract(contract_file)
    inside_records, inside_digests, inside_contracts = _inside_levels(declarations_root, contract)
    profile = PROFILES[language]
    scan = (
        scan_dart_repository(source_root, contract, roots=roots, namespace=namespace)
        if language == "dart"
        else scan_repository(
            source_root, contract, source_paths=source_paths, roots=roots, namespace=namespace
        )
    )
    _add_inside_violations(scan, inside_contracts)
    if git_head == "unknown" or dirty == "unknown":
        _add_git_failure(scan, git_head, dirty)
    # AD-2: mypy cannot assign TypedDict records to RawJson, so the canonical model stays open.
    model: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "analyzer": {
            "name": profile.analyzer,
            "version": ANALYZER_VERSION,
            "code_digest": analyzer_code_digest(),
        },
        "source": {
            "git_head": git_head,
            "dirty": dirty,
            "source_digest": scan.source_digest,
            "scope": [f"{source}/**/*{profile.source_suffix}" for source in roots],
        },
        "contract": {
            "schema_version": contract.schema_version,
            "digest": _contract_tree_digest(contract_digest, inside_digests),
            "path": contract_reference,
        },
        "coverage": scan.coverage,
        "metrics": _metrics(scan, contract),
        "declarations": _declaration_records(contract, scan, inside_records, contract_reference),
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
    # AD-97: a signal the profile never produces is null, so a claim on it reads UNKNOWN.
    for section in profile.absent_sections:
        model[section] = None
    return model, 0 if scan.coverage["status"] == "PASS" else 2
