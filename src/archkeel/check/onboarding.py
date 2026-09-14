# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Derive a first architecture contract from one observation of the repository."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Final

from archkeel.ir.codec import CONTRACT_SCHEMA_VERSION, contract_bytes
from archkeel.ir.model import (
    ArchitectureContract,
    ArchitectureRule,
    CompleteAssignmentRule,
    ComponentRole,
    ContractComponent,
    Diagnostic,
    DiagnosticError,
    ForbiddenDependencyRule,
    NoComponentCyclesRule,
    Observation,
    RunResult,
    in_scope,
)

from .ports import Analyzer, ScanConfig
from .report import observe_repository
from .validation import COMPONENT_GRAPH_MARKER, observed_component_edges

CONFIG_PATH: Final = "archkeel.toml"
CONTRACT_PATH: Final = "architecture-contract.json"
DOCUMENT_PATH: Final = "docs/architecture/architecture.md"


def detect_source(root: Path) -> tuple[str, str]:
    """Return the scan root and namespace of the only top-level package."""
    base = root / "src" if (root / "src").is_dir() else root
    packages = sorted(path for path in base.iterdir() if (path / "__init__.py").is_file())
    if len(packages) != 1:
        found = ", ".join(path.relative_to(root).as_posix() for path in packages) or "none"
        raise DiagnosticError(
            Diagnostic(
                "scope_empty",
                str(base),
                f"Expected exactly one top-level Python package; found {found}.",
                "Pass --source <directory> and --namespace <package> to archkeel init.",
            )
        )
    return packages[0].relative_to(root).as_posix(), packages[0].name


def _identifier(label: str) -> str:
    return label.upper().replace("_", "-")


def _has_cycle(labels: tuple[str, ...], edges: frozenset[tuple[str, str]]) -> bool:
    targets = {label: {target for source, target in edges if source == label} for label in labels}
    visiting: set[str] = set()
    done: set[str] = set()

    def visit(label: str) -> bool:
        if label in visiting:
            return True
        if label in done:
            return False
        visiting.add(label)
        found = any(visit(target) for target in targets[label])
        visiting.discard(label)
        done.add(label)
        return found

    return any(visit(label) for label in labels)


def draft_contract(
    observation: Observation, namespace: str
) -> tuple[ArchitectureContract, frozenset[tuple[str, str]]]:
    """Close the component world: forbid every pair the observed imports do not use."""
    depth = len(namespace.split("."))
    labels = tuple(
        sorted(
            {
                name.split(".")[depth]
                for record in observation.records("modules") or ()
                if isinstance((name := record.data.get("qualified_name")), str)
                and name != namespace
                and in_scope(name, namespace)
            }
        )
    )
    components = tuple(
        ContractComponent(
            f"COMP-{_identifier(label)}",
            label,
            ComponentRole.COMPONENT,
            (f"{namespace}.{label}",),
            (),
            (),
            (DOCUMENT_PATH,),
        )
        for label in labels
    )
    edges = observed_component_edges(
        ArchitectureContract(CONTRACT_SCHEMA_VERSION, components, ()), observation
    )
    rules: list[ArchitectureRule] = [
        ForbiddenDependencyRule(
            f"DEP-{_identifier(source)}-NO-{_identifier(target)}",
            "forbidden_dependency",
            f"{namespace}.{source}",
            f"{namespace}.{target}",
            True,
            f"TODO: explain why {source} must not depend on {target}.",
            (DOCUMENT_PATH,),
        )
        for source in labels
        for target in labels
        if source != target and (source, target) not in edges
    ]
    rules.append(
        CompleteAssignmentRule(
            "ASSIGNMENT-COMPLETE",
            "complete_assignment",
            namespace,
            "TODO: explain why every module needs exactly one owning component.",
            (DOCUMENT_PATH,),
        )
    )
    if not _has_cycle(labels, edges):
        rules.append(
            NoComponentCyclesRule(
                "COMPONENT-NO-CYCLES",
                "no_component_cycles",
                "TODO: explain why components must stay acyclic.",
                (DOCUMENT_PATH,),
            )
        )
    return ArchitectureContract(CONTRACT_SCHEMA_VERSION, components, tuple(rules)), edges


def architecture_document(
    namespace: str, contract: ArchitectureContract, edges: frozenset[tuple[str, str]]
) -> str:
    """Write the provenance page whose marked graph validate compares with observed imports."""
    rows = "\n".join(
        f"| `{component.label}` | `{component.packages[0]}` | TODO: describe the responsibility. |"
        for component in contract.components
    )
    graph = "".join(f"    {source} --> {target}\n" for source, target in sorted(edges))
    return (
        f"# {namespace} architecture\n\n"
        "Generated by `archkeel init` from observed imports. Replace every TODO with the\n"
        "owner's intent, then run `archkeel validate`.\n\n"
        "| Component | Package | Responsibility |\n|---|---|---|\n"
        f"{rows}\n\n{COMPONENT_GRAPH_MARKER}\n```mermaid\ngraph TD\n{graph}```\n"
    )


def run_init(
    root: Path,
    *,
    source: str | None,
    namespace: str | None,
    force: bool,
    analyzer: Analyzer,
) -> tuple[RunResult, dict[str, bytes]]:
    """Observe the repository and return the onboarding files without writing them."""
    if source is None or namespace is None:
        if source is not None or namespace is not None:
            raise ValueError("pass both --source and --namespace, or neither")
        source, namespace = detect_source(root)
    existing = [
        path for path in (CONFIG_PATH, CONTRACT_PATH, DOCUMENT_PATH) if (root / path).exists()
    ]
    if existing and not force:
        raise DiagnosticError(
            Diagnostic(
                "existing_files",
                ", ".join(existing),
                "Onboarding would replace files that already exist.",
                "Rerun archkeel init with --force to replace them.",
            )
        )
    config = ScanConfig((source,), namespace, CONTRACT_PATH, "")
    with TemporaryDirectory(prefix="archkeel-init-") as temporary:
        scaffold = Path(temporary)
        (scaffold / CONTRACT_PATH).write_bytes(
            contract_bytes(ArchitectureContract(CONTRACT_SCHEMA_VERSION, (), ()))
        )
        observed = observe_repository(root, config, analyzer, contract_root=scaffold)
    if observed.diagnostics or observed.observation is None:
        return RunResult(
            "init", 2, diagnostics=observed.diagnostics, coverage=observed.coverage
        ), {}
    contract, edges = draft_contract(observed.observation, namespace)
    files = {
        CONFIG_PATH: (
            f"[scan]\nroots = [{json.dumps(source)}]\nnamespace = {json.dumps(namespace)}\n"
            f"contract = {json.dumps(CONTRACT_PATH)}\n"
        ).encode(),
        CONTRACT_PATH: contract_bytes(contract),
        DOCUMENT_PATH: architecture_document(namespace, contract, edges).encode(),
    }
    result = RunResult(
        "init",
        0,
        observation_complete="PASS",
        expectation_fulfilled="n/a",
        coverage=observed.coverage,
        python_version=observed.observation.python_version,
        artifact=CONTRACT_PATH,
    )
    return result, files
