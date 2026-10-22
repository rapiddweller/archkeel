# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Contract reference and ownership diagnostics."""

from __future__ import annotations

from pathlib import Path

from archkeel.ir.codec import (
    InsideContractTree,
    contract_digest,
    contract_provenance_locations,
    load_inside_contract_tree,
)
from archkeel.ir.facts import SourceNameVisibility
from archkeel.ir.model import (
    ArchitectureContract,
    ContractComponent,
    Diagnostic,
    Observation,
    contract_relative_path,
    in_scope,
    module_references,
)
from archkeel.ir.model import DiagnosticCode as _DiagnosticCode
from archkeel.ir.profiles import PROFILES
from archkeel.ir.source_records import source_name_visibility as _source_name_visibility

from ..ports import ScanConfig
from .diagnostics import _diagnostic, _sorted
from .public_api import _entry_module, _scanned_modules


def _namespace_references(
    contract: ArchitectureContract, sdk_libraries: frozenset[str]
) -> list[tuple[str, str]]:
    """Every contract-declared name that must resolve inside the scan namespace.

    They are the entries `ir.model.module_references` marks held, from the list a rename
    rewrites (AD-105).
    """
    return [
        (item.pointer, _entry_module(item.value))
        for item in module_references(contract, external=sdk_libraries)
        if item.held
    ]


def _entry_ownership_diagnostics(
    contract: ArchitectureContract, component: ContractComponent, index: int, field: str
) -> list[Diagnostic]:
    """Require each entry of one `public` or `planned` list to be owned, never underscore-named."""
    entries = component.public if field == "public" else component.planned
    diagnostics = []
    for item, entry in enumerate(entries or ()):
        module, _, name = entry.partition(":")
        pointer = f"/components/{index}/{field}/{item}"
        if contract.component_for(module) is not component:
            diagnostics.append(
                _diagnostic(
                    _DiagnosticCode.REFERENCE_PUBLIC_OWNER,
                    pointer,
                    entry,
                    "The public entry's module is not owned by this component.",
                    "Move the entry to its owning component or correct the module.",
                )
            )
        if _source_name_visibility(name) is SourceNameVisibility.PRIVATE:
            diagnostics.append(
                _diagnostic(
                    _DiagnosticCode.REFERENCE_PUBLIC_UNDERSCORE,
                    pointer,
                    entry,
                    "Underscore names are never public.",
                    "Remove the entry or expose a non-underscore name.",
                )
            )
    return diagnostics


def _public_diagnostics(contract: ArchitectureContract) -> list[Diagnostic]:
    """Require each public and planned entry to be owned by its component, never underscore.

    A planned entry names something the component will own once built, so it is held to the
    same ownership and underscore checks as `public` (AD-56); reusing them here means a typo
    in a planned facade name is caught the same way a typo in a live one already is.
    """
    diagnostics = []
    for index, component in enumerate(contract.components):
        diagnostics.extend(_entry_ownership_diagnostics(contract, component, index, "public"))
        diagnostics.extend(_entry_ownership_diagnostics(contract, component, index, "planned"))
    return diagnostics


def repository_file(repository: Path, value: str) -> Path | None:
    """Resolve a contract-declared repository path, or None when it is unsafe or missing.

    Every path a contract names is attacker-adjacent input: it may escape the repository
    with `..`, with an absolute path or with a Windows separator. That judgement now lives in
    `ir` so the analyzer applies the same one without importing `check` (AD-34); what stays
    here is the filesystem check, which `ir` may not perform (AD-17).
    """
    relative = contract_relative_path(value)
    if relative is None:
        return None
    target = (repository / relative).resolve()
    if not target.is_relative_to(repository) or not target.is_file():
        return None
    return target


def _inside_contract_tree(
    repository: Path, contract_path: str, contract: ArchitectureContract
) -> InsideContractTree | None:
    """Load mounted declarations with the same path checks used by observation snapshots."""
    root = repository.resolve()
    target = repository_file(root, contract_path)
    if target is None:
        return None
    identity = target.relative_to(root).as_posix()

    def read_inside(path: str) -> tuple[bytes, str]:
        child = repository_file(root, path)
        if child is None:
            raise ValueError("file is missing or outside the repository")
        return child.read_bytes(), child.relative_to(root).as_posix()

    return load_inside_contract_tree(
        identity,
        contract,
        contract_digest(contract),
        identity,
        read_inside,
    )


def reference_diagnostics(
    root: Path,
    config: ScanConfig,
    contract: ArchitectureContract,
    observation: Observation | None = None,
) -> tuple[Diagnostic, ...]:
    """Validate repository-dependent namespace, package and provenance references."""
    # AD-97: a forbidden SDK library (`dart.io`) is a real target outside the namespace.
    names = _namespace_references(contract, PROFILES[config.language].sdk_libraries)
    diagnostics = [
        _diagnostic(
            _DiagnosticCode.REFERENCE_NAMESPACE,
            pointer,
            value,
            f"The reference is outside namespace {config.namespace}.",
            "Use a qualified name inside the configured namespace.",
        )
        for pointer, value in names
        if not in_scope(value, config.namespace)
    ]
    diagnostics.extend(_public_diagnostics(contract))
    repository = root.resolve()
    for pointer, values in contract_provenance_locations(contract):
        for index, value in enumerate(values):
            if repository_file(repository, value) is None:
                diagnostics.append(
                    _diagnostic(
                        _DiagnosticCode.REFERENCE_PROVENANCE,
                        f"{pointer}/{index}",
                        value,
                        "The provenance file is missing or outside the repository.",
                        "Reference an existing repository-relative evidence file.",
                    )
                )
    if observation is not None:
        modules = _scanned_modules(observation)
        for component_index, component in enumerate(contract.components):
            for package_index, package in enumerate(component.packages):
                if not any(in_scope(module, package) for module in modules):
                    diagnostics.append(
                        _diagnostic(
                            _DiagnosticCode.REFERENCE_PACKAGE_UNSCANNED,
                            f"/components/{component_index}/packages/{package_index}",
                            package,
                            "The component package has no scanned Python module.",
                            "Correct the package or include it in scan.roots.",
                        )
                    )
            for exact_index, module in enumerate(component.exact_modules or ()):
                if module not in modules:
                    diagnostics.append(
                        _diagnostic(
                            _DiagnosticCode.REFERENCE_PACKAGE_UNSCANNED,
                            f"/components/{component_index}/exact_modules/{exact_index}",
                            module,
                            "The exact module has no scanned source file.",
                            "Correct the exact module or include its file in scan.roots.",
                        )
                    )
    return _sorted(diagnostics)
