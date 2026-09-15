# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Compose the canonical Python architecture report."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from archkeel.ir.model import SCHEMA_VERSION, ArchitectureContract, EvidenceClass

from .contract import load_contract, project_declarations
from .records import ANALYZER_VERSION, RawRecord, analyzer_code_digest, classified, stable_id
from .scanner import ScanResult, scan_repository

DEFAULT_CONTRACT = Path("docs/architecture/architecture-contract.json")


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
    package_cycles = [item for item in scan.cycles if item["data"]["level"] == "package"]
    module_cycles = [item for item in scan.cycles if item["data"]["level"] == "module"]
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
                "Underscore-private symbol crossings",
                len(private_crossings),
                "api",
                fact_ids=[item["id"] for item in private_crossings],
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
) -> tuple[dict[str, Any], int]:
    """Analyze explicit source bytes and metadata without consulting Git."""
    source_root = source_root.resolve()
    declarations_root = (contract_root or source_root).resolve()
    contract_file = contract_path or declarations_root / DEFAULT_CONTRACT
    if not contract_file.is_absolute():
        contract_file = declarations_root / contract_file
    contract, contract_digest = load_contract(contract_file)
    scan = scan_repository(
        source_root, contract, source_paths=source_paths, roots=roots, namespace=namespace
    )
    if git_head == "unknown" or dirty == "unknown":
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
    # AD-2: mypy cannot assign TypedDict records to RawJson, so the canonical model stays open.
    model: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "analyzer": {
            "name": "archkeel-python-analyzer",
            "version": ANALYZER_VERSION,
            "code_digest": analyzer_code_digest(),
        },
        "source": {
            "git_head": git_head,
            "dirty": dirty,
            "source_digest": scan.source_digest,
            "scope": [f"{source}/**/*.py" for source in roots],
        },
        "contract": {
            "schema_version": contract.schema_version,
            "digest": contract_digest,
            "path": contract_file.relative_to(declarations_root).as_posix(),
        },
        "coverage": scan.coverage,
        "metrics": _metrics(scan, contract),
        "declarations": project_declarations(contract),
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
        "typing_signals": scan.typing_signals,
        "constructs": scan.constructs,
        "contexts": scan.contexts,
        "context_evidence": scan.context_evidence,
        "violations": scan.violations,
        "unknowns": scan.unknowns,
        "evidence": scan.evidence,
    }
    return model, 0 if scan.coverage["status"] == "PASS" else 2
