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
from archkeel.ir.decisions import (
    dependency_binding_id,
    numeric_operand_inventory_binding_id,
    protocol_declaration_result_digest,
    rule_evaluation_binding_id,
)
from archkeel.ir.digest import package_digest
from archkeel.ir.facts import ResolutionRole as _ResolutionRole
from archkeel.ir.facts import (
    RuntimeRequirementState,
    SourceFacts,
    SourceResolution,
    SourceSectionName,
    dart_module_name,
    parse_source_resolution,
)
from archkeel.ir.facts_codec import (
    RawRecord,
    classified,
    file_evidence,
    parse_evidence,
    parse_record,
)
from archkeel.ir.facts_validation import validate_source_bindings
from archkeel.ir.identity import module_identity
from archkeel.ir.model import (
    SCHEMA_VERSION,
    ArchitectureContract,
    EvidenceClass,
    GraphTopologyLevel,
    LayerOrderRule,
    Observation,
    Section,
    contract_relative_path,
    parse_graph_topology_level,
    stable_id,
)
from archkeel.ir.profiles import PROFILES, Language, Profile, UnmeasurableScalar

from .declarations import load_contract, project_declarations, project_inside_declarations
from .evaluation.evaluate import ScanResult, evaluate_source
from .evaluation.rules import public_api_exposed_types
from .ports import SourceCollector
from .python_profile import is_crossing_import
from .runtime import has_invalid_python_requirement, runtime_diagnostic

OBSERVATION_VERSION = "0.75.0"

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
        if is_crossing_import(
            item["data"]["symbol"],
            item["data"]["source_package"],
            item["data"]["target_package"],
            item["data"]["target_module"],
            private=True,
        )
    ]
    private_attribute_limits = [
        item for item in scan.unknowns if item["kind"] == "private_attribute_access_limit"
    ]
    package_cycles = [
        item
        for item in scan.cycles
        if parse_graph_topology_level(item["data"]["level"]) is GraphTopologyLevel.PACKAGE
    ]
    module_cycles = [
        item
        for item in scan.cycles
        if parse_graph_topology_level(item["data"]["level"]) is GraphTopologyLevel.MODULE
    ]
    rollup_only = [item for item in package_cycles if not item["data"]["backed_by"]]
    unresolved_calls = [
        item
        for item in scan.calls
        if parse_source_resolution(item["data"]["status"]) is SourceResolution.UNRESOLVED
    ]
    resolved_calls = [
        item
        for item in scan.calls
        if parse_source_resolution(item["data"]["status"]) is SourceResolution.RESOLVED
    ]
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
                None
                if SourceSectionName.SYMBOLS in profile.absent_sections
                or (
                    SourceSectionName.SYMBOLS in profile.optional_sections
                    and SourceSectionName.SYMBOLS not in scan.observed_sections
                )
                else len(scan.symbols),
                "components",
                fact_ids=(
                    [item["id"] for item in scan.symbols]
                    if SourceSectionName.SYMBOLS not in profile.absent_sections
                    and not (
                        SourceSectionName.SYMBOLS in profile.optional_sections
                        and SourceSectionName.SYMBOLS not in scan.observed_sections
                    )
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
                "Contract violations",
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
                    if parse_graph_topology_level(item["data"]["level"])
                    is GraphTopologyLevel.PACKAGE
                    and (item["data"]["source"], item["data"]["target"]) in forbidden_package_edges
                ],
            ),
            _metric(
                "private_crossings",
                "Confirmed private symbol crossings",
                None
                if UnmeasurableScalar.PRIVATE_CROSSINGS in profile.unmeasured
                else len(private_crossings),
                "api",
                fact_ids=(
                    [item["id"] for item in private_crossings]
                    if UnmeasurableScalar.PRIVATE_CROSSINGS not in profile.unmeasured
                    else None
                ),
            ),
            _metric(
                "untyped_private_accesses",
                "Private attribute accesses through untyped or Any parameters",
                None
                if UnmeasurableScalar.UNTYPED_PRIVATE_ACCESSES in profile.unmeasured
                else len(private_attribute_limits),
                "api",
            ),
            _metric(
                "typing_signals",
                "Typing & dynamic signals",
                None
                if SourceSectionName.TYPING_SIGNALS in profile.absent_sections
                or UnmeasurableScalar.TYPING_POSITIONS in profile.unmeasured
                else len(scan.typing_signals),
                "types",
                fact_ids=(
                    [item["id"] for item in scan.typing_signals]
                    if SourceSectionName.TYPING_SIGNALS not in profile.absent_sections
                    and UnmeasurableScalar.TYPING_POSITIONS not in profile.unmeasured
                    else None
                ),
            ),
            _metric(
                "unresolved_calls",
                "Unresolved recorded call sites"
                if profile.analyzer == "archkeel-typescript-imports"
                else "Unresolved calls",
                None
                if SourceSectionName.CALLS not in scan.observed_sections
                else scan.coverage["calls_unresolved"],
                "calls",
                fact_ids=(
                    [item["id"] for item in unresolved_calls]
                    if SourceSectionName.CALLS in scan.observed_sections
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
                "Uniquely resolved recorded call sites"
                if profile.analyzer == "archkeel-typescript-imports"
                else "Uniquely resolved calls",
                None
                if SourceSectionName.CALLS not in scan.observed_sections
                else f"{scan.coverage['call_resolution_percent']}%",
                "calls",
                fact_ids=(
                    [item["id"] for item in resolved_calls]
                    if SourceSectionName.CALLS in scan.observed_sections
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
        name = _declared_module_name(path, roots, namespace, Language.DART)
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
    """Bind public-type evidence before projecting declarations (AD-70)."""
    types_by_entry = (
        public_api_exposed_types(
            contract.declarations.public_api if contract.declarations is not None else (),
            scan.symbols,
            scan.imports,
            scan.modules,
            contract,
            unknowns=scan.unknowns,
            type_shapes=scan.type_shapes,
        )
        if SourceSectionName.SYMBOLS in scan.observed_sections
        else {}
    )
    records = [
        *project_declarations(
            contract,
            contract_path,
            types_by_entry=types_by_entry,
        ),
        *inside_records,
    ]
    roots, namespace = module_scope
    dart_names = (
        _dart_target_names(records, scan, roots, namespace) if language == Language.DART else {}
    )
    for record in records:
        data = record["data"]
        if record["kind"] != "module_target" or "path" not in data:
            continue
        path = data["path"]
        if not isinstance(path, str):
            continue
        qualified_name = (
            dart_names.get(record["id"])
            if language == Language.DART
            else _declared_module_name(path, roots, namespace, language)
        )
        if qualified_name is not None:
            record["data"] = {**record["data"], "qualified_name": qualified_name}
    scan.unknowns = sorted(scan.unknowns, key=lambda item: item["id"])
    return records


def _declared_module_name(
    path: str, roots: tuple[str, ...], namespace: str, language: Language = Language.PYTHON
) -> str | None:
    if language == Language.DART:
        source_path = PurePosixPath(path)
        if source_path.suffix != ".dart":
            return None
        names = [
            dart_module_name(source_path.relative_to(PurePosixPath(root)).as_posix())
            for root in roots
            if source_path.is_relative_to(PurePosixPath(root))
        ]
        return f"{namespace}.{names[0]}" if len(names) == 1 and names[0] is not None else None
    if language == Language.TYPESCRIPT:
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


def _layer_order_evidence(
    scan: ScanResult,
    root: Path,
    contract: ArchitectureContract,
    contract_path: str,
    contract_digest: str,
    mounts: list[InsideContractMount],
) -> None:
    """Bind declaration-only assessments to the bytes Core actually read, never an import."""
    evidence = {item["id"]: item for item in scan.evidence}
    levels = [(contract_path, contract_digest, contract.rules)] + [
        (mount.path, mount.digest, mount.contract.rules) for mount in mounts
    ]
    for path, digest, rules in levels:
        identifiers: set[str] = {rule.id for rule in rules if isinstance(rule, LayerOrderRule)}
        if not identifiers:
            continue
        receipts = [
            item
            for item in scan.scope_observations
            if item["kind"] == "rule_evaluation" and identifiers.intersection(item["rule_ids"])
        ]
        try:
            contract_file: Path = root / path
            content = contract_file.read_bytes()
            if hashlib.sha256(content).hexdigest() != digest:
                raise ValueError("Contract bytes changed after Core read them.")
            text: str = str(content, "utf-8")
            evidence_id = file_evidence(evidence, path, text.splitlines())
        except (OSError, UnicodeError, ValueError) as error:
            for receipt in receipts:
                receipt["data"]["assessment_complete"] = False
            scan.violations = [
                item for item in scan.violations if not identifiers.intersection(item["rule_ids"])
            ]
            _record_inside_failures(
                scan,
                [
                    classified(
                        item_id=stable_id("UNKNOWN-DECLARATION-SOURCE", path),
                        evidence_class=EvidenceClass.UNKNOWN,
                        area="analysis_coverage",
                        kind="declaration_source_unavailable",
                        title="Layer permission assessment lacks authenticated contract source",
                        subjects=[path],
                        rule_ids=sorted(identifiers),
                        data={"path": path, "reason": str(error)},
                    )
                ],
            )
            continue
        for receipt in receipts:
            receipt["evidence_ids"] = [evidence_id]
            receipt["data"]["contract_path"] = path
            receipt["data"]["contract_digest"] = digest
        for violation in scan.violations:
            if identifiers.intersection(violation["rule_ids"]):
                violation["evidence_ids"] = [evidence_id]
    scan.evidence = sorted(evidence.values(), key=lambda item: item["id"])


def _dependency_binding_id(
    scan: ScanResult, declarations: list[RawRecord], *, include_calls: bool = False
) -> str:
    return dependency_binding_id(
        (
            Section(name, tuple(parse_record(item) for item in records))
            for name, records in (
                ("modules", scan.modules),
                ("imports", scan.imports),
                ("symbols", scan.symbols),
                ("references", scan.references),
                ("calls", scan.calls),
                ("declarations", declarations),
            )
        ),
        (parse_record(item) for item in scan.coverage["failures"]),
        (parse_evidence(item) for item in scan.evidence),
        include_calls=include_calls,
    )


def _certify_call_owner_scopes(
    scan: ScanResult, facts: SourceFacts, contract_digest: str, declarations: list[RawRecord]
) -> None:
    rules = {
        r["id"]
        for r in declarations
        if r["kind"] in {"call_owner", "forbidden_call_argument", "catalog_argument", "catalog_use"}
    }
    receipts = [
        r
        for r in scan.scope_observations
        if r["kind"] == "rule_evaluation" and len(r["rule_ids"]) == 1 and r["rule_ids"][0] in rules
    ]
    if not receipts:
        return
    proof = {
        "source_digest": facts.source.source_digest,
        "source_scope": list(facts.source.scope),
        "contract_digest": contract_digest,
        "selected_files": list(facts.coverage.selected_files),
    }
    inventory_binding_id = _dependency_binding_id(scan, declarations, include_calls=True)
    for receipt in receipts:
        receipt["data"]["call_scope_proof"] = {
            **proof,
            "binding_id": rule_evaluation_binding_id(
                inventory_binding_id, parse_record(receipt), SCHEMA_VERSION
            ),
        }


def _certify_numeric_operand_scopes(
    scan: ScanResult,
    facts: SourceFacts,
    contract_digest: str,
    declarations: list[RawRecord],
) -> None:
    """Bind numeric claims to selected inputs, contracts and the complete fact inventory."""
    identifiers = {item["id"] for item in declarations if item["kind"] == "bounded_numeric_operand"}
    receipts = [
        item
        for item in scan.scope_observations
        if item["kind"] == "rule_evaluation"
        and len(item["rule_ids"]) == 1
        and item["rule_ids"][0] in identifiers
    ]
    if not receipts:
        return
    modules = tuple(parse_record(item) for item in scan.modules)
    constructs = tuple(
        parse_record(item) for item in scan.constructs if item["kind"] == "numeric_operand"
    )
    rule_declarations = tuple(parse_record(item) for item in declarations)
    failures = tuple(parse_record(item) for item in scan.coverage["failures"])
    evidence = tuple(parse_evidence(item) for item in scan.evidence)
    inventory_binding = numeric_operand_inventory_binding_id(
        (
            Section("modules", modules),
            Section("constructs", constructs),
            Section("declarations", rule_declarations),
        ),
        failures,
        evidence,
    )
    selected_files = tuple(sorted(facts.coverage.selected_files))
    module_files = {
        item.data.get("file") for item in modules if isinstance(item.data.get("file"), str)
    }
    physically_complete = (
        bool(selected_files)
        and set(selected_files) == module_files
        and facts.coverage.files_read == facts.coverage.files_parsed == len(selected_files)
        and scan.coverage["files_discovered"]
        == scan.coverage["files_read"]
        == scan.coverage["files_parsed"]
        == len(selected_files)
        and scan.coverage["status"] == "PASS"
        and not failures
    )
    for receipt in receipts:
        receipt["data"]["assessment_complete"] = (
            "assessment_complete" in receipt["data"]
            and receipt["data"]["assessment_complete"] is True
            and physically_complete
        )
        proof = {
            "source_digest": facts.source.source_digest,
            "source_scope": list(facts.source.scope),
            "contract_digest": contract_digest,
            "observation_schema_version": SCHEMA_VERSION,
            "scope": receipt["data"]["scope"] if "scope" in receipt["data"] else None,
            "selected_files": list(selected_files),
            "module_ids": sorted(item.id for item in modules),
            "operation_ids": sorted(item.id for item in constructs),
        }
        receipt["data"]["numeric_scope_proof"] = {
            **proof,
            "binding_id": rule_evaluation_binding_id(
                inventory_binding, parse_record(receipt), SCHEMA_VERSION
            ),
        }


def _certify_protocol_declaration_scopes(
    scan: ScanResult, facts: SourceFacts, contract_digest: str, declarations: list[RawRecord]
) -> None:
    rules = {r["id"] for r in declarations if r["kind"] == "protocol_declarations"}
    receipts = [
        r
        for r in scan.scope_observations
        if r["kind"] == "rule_evaluation" and len(r["rule_ids"]) == 1 and r["rule_ids"][0] in rules
    ]
    if not receipts:
        return
    proof = {
        "source_digest": facts.source.source_digest,
        "source_scope": list(facts.source.scope),
        "contract_digest": contract_digest,
        "selected_files": list(facts.coverage.selected_files),
    }
    inventory_binding_id = _dependency_binding_id(scan, declarations)
    all_records = tuple(
        parse_record(item)
        for group in (
            scan.violations,
            scan.unknowns,
        )
        for item in group
    )
    for receipt in receipts:
        receipt_id = receipt["rule_ids"][0]
        receipt["data"]["protocol_scope_proof"] = {
            **proof,
            "result_digest": protocol_declaration_result_digest(all_records, receipt_id),
            "binding_id": rule_evaluation_binding_id(
                inventory_binding_id, parse_record(receipt), SCHEMA_VERSION
            ),
        }


def _certify_dependency_scopes(
    scan: ScanResult, facts: SourceFacts, contract_digest: str, declarations: list[RawRecord]
) -> None:
    """Bind complete requires receipts to validated physical inventory and runtime."""
    if scan.coverage["status"] == "PASS":
        return
    requires = {item["id"] for item in declarations if item["kind"] == "complete_requires"}
    receipts = [
        item
        for item in scan.scope_observations
        if item["kind"] == "rule_evaluation"
        and len(item["rule_ids"]) == 1
        and item["rule_ids"][0] in requires
    ]
    for receipt in receipts:
        receipt["data"]["assessment_complete"] = False
    selected = set(facts.coverage.selected_files)
    if (
        not selected
        or scan.coverage["rules"] != "PASS"
        or facts.coverage.files_read != len(selected)
        or facts.coverage.files_parsed != len(selected)
        or selected != {item.path for item in facts.inputs if item.role == _ResolutionRole.SELECTED}
        or runtime_diagnostic(facts.runtime) is not None
    ):
        return
    records = {
        record["id"]: parse_record(record)
        for values in (scan.modules, scan.symbols, scan.imports, scan.references, scan.unknowns)
        for record in values
    }
    evidence = {item["id"]: parse_evidence(item) for item in scan.evidence}
    paths = {item.module: item.rel_path for item in facts.files}
    gaps = [parse_record(item) for item in scan.coverage["failures"]]
    if not gaps or any(gap.kind != "source_resolution_gap" for gap in gaps):
        return
    try:
        validate_source_bindings(
            gaps,
            paths,
            {},
            evidence,
            import_ids=(),
            selected_inputs=selected,
            source_records=records,
            allow_script_effects=facts.profile == PROFILES[Language.TYPESCRIPT].analyzer,
        )
    except ValueError:
        return
    origins = [(gap, gap.data.get("source_module", gap.data.get("module"))) for gap in gaps]
    proof = {
        "binding_id": _dependency_binding_id(scan, declarations),
        "source_digest": facts.source.source_digest,
        "contract_digest": contract_digest,
        "selected_files": sorted(selected),
        "gap_ids": sorted(gap.id for gap in gaps),
        "module_ids": sorted(item["id"] for item in scan.modules),
        "import_ids": sorted(item["id"] for item in scan.imports),
        "runtime": {
            "name": facts.runtime.name,
            "version": facts.runtime.version,
            "required": facts.runtime.required,
            "requirement_state": facts.runtime.requirement_state,
        },
    }
    for receipt in receipts:
        if not any(
            gap.data.get("resolution_dimension") == "imports" and module in receipt["subjects"]
            for gap, module in origins
        ):
            receipt["data"]["dependency_scope_proof"] = proof
            receipt["data"]["assessment_complete"] = True


def assemble_observation(
    facts: SourceFacts,
    *,
    contract_root: Path,
    contract_path: Path | None = None,
    roots: tuple[str, ...] = ("src",),
    namespace: str = "src",
    language: Language = Language.PYTHON,
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
    _layer_order_evidence(
        scan, declarations_root, contract, contract_reference, contract_digest, inside_contracts
    )
    _record_inside_failures(scan, inside_failures)
    if git_head == "unknown" or dirty == "unknown":
        _add_git_failure(scan, git_head, dirty)
    scope = roots, namespace
    declarations = _declaration_records(
        contract, scan, inside_records, contract_reference, scope, language
    )
    _certify_dependency_scopes(scan, facts, full_contract_digest, declarations)
    _certify_call_owner_scopes(scan, facts, full_contract_digest, declarations)
    _certify_numeric_operand_scopes(scan, facts, full_contract_digest, declarations)
    _certify_protocol_declaration_scopes(scan, facts, full_contract_digest, declarations)
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
    requirement_state = facts.runtime.requirement_state
    if requirement_state == RuntimeRequirementState.DECLARED and has_invalid_python_requirement(
        facts.runtime
    ):
        requirement_state = RuntimeRequirementState.REQUIREMENT_INVALID
    model["runtime"] = {
        "name": facts.runtime.name,
        "version": facts.runtime.version,
        "required": facts.runtime.required,
        "requirement_state": requirement_state,
    }
    if language == Language.PYTHON and facts.runtime.name == "python":
        model["python_version"] = facts.runtime.version
    if language != Language.PYTHON or facts.adapter.name != profile.analyzer:
        model["producer"] = {
            "name": facts.adapter.name,
            "version": facts.adapter.version,
            "code_digest": facts.adapter.code_digest,
        }
    # AD-97: a signal the profile never produces is null, so a claim on it reads UNKNOWN.
    for section in profile.absent_sections:
        model[section] = None
    for section in profile.optional_sections:
        if section not in scan.observed_sections:
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
    language: Language = Language.PYTHON,
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
        if language == Language.TYPESCRIPT
        else DartSettings()
        if language == Language.DART
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
