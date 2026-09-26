# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Validate architecture-contract quality against typed observations."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Final, TypeVar

from archkeel.ir.baseline import (
    KnownViolation,
    ValidationBaseline,
    compare_violations,
    observed_violations,
    violation_drift_counts,
)
from archkeel.ir.codec import (
    CONTRACT_SCHEMA_VERSION,
    ContractVersionError,
    InsideContractTree,
    absent_contract_digest,
    amendment_bytes,
    baseline_bytes,
    contract_digest,
    contract_provenance_paths,
    decode_json,
    load_inside_contract_tree,
    parse_amendment,
    parse_contract,
    parse_validation_baseline,
)
from archkeel.ir.decisions import (
    agent_decisions,
    open_decisions,
    review_claims,
    violation_counts,
)
from archkeel.ir.interfaces import interface_budgets
from archkeel.ir.measurements import (
    MeasurementBudget,
    NameBudgetKind,
    RatchetError,
    budget_label,
    budget_regressions,
    compare_budgets,
    name_drift,
    selected_budgets,
)
from archkeel.ir.model import (
    AllowedDependencyRule,
    ArchitectureContract,
    CompatibilityShim,
    CompleteRequiresRule,
    ContractComponent,
    ContractDeclarations,
    Diagnostic,
    DiagnosticCode,
    ForbiddenDependencyRule,
    InterfaceBoundaryRule,
    InterfaceBudgetResult,
    JsonValue,
    NoComponentCyclesRule,
    Observation,
    Record,
    RecordData,
    RunResult,
    UnresolvedCallChange,
    contract_relative_path,
    in_scope,
    module_references,
    text_value,
)
from archkeel.ir.profiles import PROFILES
from archkeel.ir.renames import Renamed, module_layouts, observed_names, renames_since
from archkeel.ir.widening import (
    Amendment,
    baseline_widenings,
    contract_widenings,
    measurement_budget_widenings,
    verify_amendment,
)

from .git import GitError, MissingBlobError, read_blob, tracked_paths, working_tree_paths
from .ports import Analyzer, FilesToWrite, ScanConfig
from .ratchets import measure_python_ratchets, unresolved_call_changes
from .report import observe_repository
from .run import inspect_observation, observe_revision
from .snapshot import SnapshotError

COMPONENT_GRAPH_MARKER = "<!-- archkeel-component-graph -->"
# AD-57: a second, independent marker for the graph the contract permits, beside the one
# above for the graph the code observes. A page may carry either, both or neither.
TARGET_GRAPH_MARKER = "<!-- archkeel-target-graph -->"
# One noun and two source phrases per marker - the claim reads "differs from X", the remedy
# "regenerate ... from Y" - so graph.count/graph.drift read the same for both markers and a
# diagnostic's subject always names which one it is about. Each marker also names its own
# comparison, because the component graph compares code while the target graph compares the
# contract.
_GRAPH_MARKERS: tuple[tuple[str, str, str, str, str, str], ...] = (
    (
        COMPONENT_GRAPH_MARKER,
        "component",
        "observed imports",
        "the observed component edges",
        "edges gone from code (drawn, not observed)",
        "edges new in code (observed, not drawn)",
    ),
    (
        TARGET_GRAPH_MARKER,
        "target",
        "the edges the contract permits",
        "the edges the contract permits",
        "edges gone from contract (drawn, not permitted)",
        "edges new in contract (permitted, not drawn)",
    ),
)
_REPEATED_RATIONALE = re.compile(r"(?:The )?\S+ does not depend on \S+\.", re.IGNORECASE)
# A requires entry states a permission, so the prohibition-shaped pattern above can never
# fire on it; its filler equivalent reads "cli depends on render." (AD-32).
_REPEATED_REQUIRES = re.compile(
    r"(?:The )?\S+ (?:depends on|requires|uses|needs) \S+\.", re.IGNORECASE
)
_PLACEHOLDER_RATIONALE = re.compile(r"(?:todo|tbd|placeholder)(?:\b|:)", re.IGNORECASE)
_GRAPH_EDGE = re.compile(r"\s*([a-z_][a-z0-9_]*)\s*-->\s*([a-z_][a-z0-9_]*)\s*")
_MERMAID_FENCE = "```mermaid\n"
_GRAPH_DECLARATION = re.compile(r"\s*(?:graph|flowchart)\b.*")
_GRAPH_COMMENT = re.compile(r"\s*%%.*")
# AD-106: the last failure of a refused --write-baseline, after every other line of the run.
_WRITE_REFUSED = (
    "--write-baseline refused: writing would accept the new or increased debt above; fix the "
    "code, or add --accept-new once an architect has decided to accept it"
)


def _diagnostic(
    code: DiagnosticCode, pointer: str, subject: str, claim: str, remedy: str
) -> Diagnostic:
    return Diagnostic("contract_invalid", subject, claim, remedy, pointer, code)


def _package_owners(contract: ArchitectureContract) -> dict[str, str]:
    return {
        package: component.label
        for component in contract.components
        for package in component.packages
    }


def observed_component_edges(
    contract: ArchitectureContract, observation: Observation
) -> frozenset[tuple[str, str]]:
    """Project module imports onto declared component labels."""
    edges: set[tuple[str, str]] = set()
    for record in observation.records("imports") or ():
        source_module = record.data.get("source_module")
        target_module = record.data.get("target_module")
        if not isinstance(source_module, str) or not isinstance(target_module, str):
            continue
        source = contract.component_for(source_module)
        target = contract.component_for(target_module)
        if source is not None and target is not None and source != target:
            edges.add((source.label, target.label))
    return frozenset(edges)


_DecisionRule = TypeVar("_DecisionRule", ForbiddenDependencyRule, AllowedDependencyRule)


def _decided_pairs(
    contract: ArchitectureContract, rule_type: type[_DecisionRule]
) -> list[tuple[str, str]]:
    """Return the component pairs one rule type decides, keyed by exact package ownership."""
    owners = _package_owners(contract)
    return [
        (owners[rule.source], owners[rule.target])
        for rule in contract.rules
        if isinstance(rule, rule_type) and rule.source in owners and rule.target in owners
    ]


def target_component_edges(contract: ArchitectureContract) -> frozenset[tuple[str, str]]:
    """The component pairs the contract permits, for `<!-- archkeel-target-graph -->` (AD-57).

    A contract states a pair may exist in one of two ways: a `requires` entry, AD-32's
    intentional grant, absence of which `complete_requires` forbids; or an `allowed_dependency`
    rule, AD-15's closed-world grant, where every pair is decided one way or the other. Both
    name a permitted pair, so the target draws their union - one rule, not a branch on which
    system a contract adopted. In practice a contract writes one or the other: a `requires`-based
    contract carries no coarse `allowed_dependency` pair and a pair-decided one carries no
    `requires` entry, so the union reduces to whichever the contract actually wrote, and a
    contract that has adopted neither permits nothing yet - the target graph is then empty.
    """
    requires_edges = {
        (component.label, entry.component)
        for component in contract.components
        for entry in component.requires or ()
    }
    return frozenset(requires_edges) | frozenset(_decided_pairs(contract, AllowedDependencyRule))


def _pair_diagnostics(
    code: DiagnosticCode, pairs: Iterable[tuple[str, str]], claim: str, remedy: str
) -> list[Diagnostic]:
    return [
        _diagnostic(code, "/rules", f"{source} -> {target}", claim, remedy)
        for source, target in pairs
    ]


def _open_decision_diagnostics(observation: Observation) -> list[Diagnostic]:
    return [
        _diagnostic(
            "decision.open",
            "/rules",
            f"{decision.source} -> {decision.target}",
            f"{decision.import_sites} import site(s) use this pair, and no rule decides it."
            if decision.observed
            else "No import uses this pair today, and no rule decides it.",
            "Allow or forbid the pair: add an allowed_dependency or forbidden_dependency rule "
            "with a rationale.",
        )
        for decision in open_decisions(observation)
    ]


def closed_world_diagnostics(
    contract: ArchitectureContract, observation: Observation
) -> tuple[Diagnostic, ...]:
    """Require each ordered component pair to be a decision, and each decision unique (AD-15)."""
    observed = observed_component_edges(contract, observation)
    forbidden_items = _decided_pairs(contract, ForbiddenDependencyRule)
    allowed_items = _decided_pairs(contract, AllowedDependencyRule)
    forbidden = set(forbidden_items)
    allowed = set(allowed_items)
    diagnostics = _open_decision_diagnostics(observation)
    diagnostics.extend(
        _pair_diagnostics(
            "closed_world.observed_forbidden",
            sorted(observed & forbidden),
            "An observed component dependency is also forbidden.",
            "Remove the dependency or correct the forbidden_dependency rule.",
        )
    )
    diagnostics.extend(
        _pair_diagnostics(
            "closed_world.duplicate",
            sorted(pair for pair, count in Counter(forbidden_items).items() if count > 1),
            "The component pair has duplicate forbidden_dependency rules.",
            "Keep one forbidden_dependency rule for this ordered component pair.",
        )
    )
    diagnostics.extend(
        _pair_diagnostics(
            "closed_world.duplicate",
            sorted(pair for pair, count in Counter(allowed_items).items() if count > 1),
            "The component pair has duplicate allowed_dependency rules.",
            "Keep one allowed_dependency rule for this ordered component pair.",
        )
    )
    diagnostics.extend(
        _pair_diagnostics(
            "decision.conflict",
            sorted(allowed & forbidden),
            "The component pair has both an allowed_dependency and a forbidden_dependency rule.",
            "Keep only one decision for this ordered component pair.",
        )
    )
    return tuple(diagnostics)


def _scanned_modules(observation: Observation) -> frozenset[str]:
    """Every module the scan actually read, by qualified name (shared with reference checks)."""
    return frozenset(
        module_name
        for record in observation.records("modules") or ()
        if isinstance((module_name := record.data.get("qualified_name")), str)
    )


def _literal_exports(observation: Observation) -> dict[str, frozenset[str]]:
    """Each scanned module's literal `__all__`, absent for a module that declares none.

    A module without `__all__` is not in the mapping at all, which is what lets a reader tell
    "this module states its surface and the name is not in it" from "this module states no
    surface", the distinction `symbols` alone cannot make for a constant or type alias.
    """
    return {
        module_name: frozenset(export for export in exports if isinstance(export, str))
        for record in observation.records("modules") or ()
        if isinstance((module_name := record.data.get("qualified_name")), str)
        and isinstance((exports := record.data.get("all_exports")), tuple)
        and exports
    }


def _entry_module(entry: str) -> str:
    return entry.partition(":")[0]


def _resolved_public_entries(
    contract: ArchitectureContract,
    known: tuple[KnownViolation, ...],
    observed: tuple[KnownViolation, ...],
    observation: Observation | None = None,
) -> tuple[tuple[str, str], ...]:
    """Return public entries proven to have lost their last importer by a 1.1 baseline.

    A role is before-evidence, not an inference from a diagnostic message.  The fingerprint's
    subjects add the imported symbol, while the role preserves source and target module
    direction.  Older baselines have no roles and therefore cannot suppress ``interface.unused``.
    """
    observed_by_fingerprint = {item.fingerprint: item for item in observed}
    resolved: set[tuple[str, str]] = set()
    public_by_component = {
        component.label: frozenset(component.public or ()) for component in contract.components
    }
    records_by_component = (
        _imports_by_target(contract, observation) if observation is not None else {}
    )
    facade_types = _facade_types(observation) if observation is not None else ()

    def add_if_unused(component: str, entry: str) -> None:
        if not _entry_used(entry, records_by_component.get(component, []), facade_types):
            resolved.add((component, entry))

    for item in known:
        if not item.roles or len(item.fingerprint.subjects) != 2:
            continue
        current = observed_by_fingerprint.get(item.fingerprint)
        if current is not None:
            continue
        gone_roles = set(item.roles)
        if len(gone_roles) != 1:
            continue
        subjects = frozenset(item.fingerprint.subjects)
        ((source_module, target_module),) = gone_roles
        if source_module not in subjects:
            continue
        target_component = contract.component_for(target_module)
        source_component = contract.component_for(source_module)
        if (
            target_component is None
            or source_component is None
            or source_component == target_component
        ):
            continue
        target_name = next((subject for subject in subjects if subject != source_module), None)
        if target_name is None or not (
            target_name == target_module or target_name.startswith(f"{target_module}.")
        ):
            continue
        public = public_by_component[target_component.label]
        if target_name == target_module and target_module in public:
            add_if_unused(target_component.label, target_module)
            continue
        symbol = target_name.removeprefix(f"{target_module}.")
        entry = f"{target_module}:{symbol}"
        if entry in public:
            add_if_unused(target_component.label, entry)
    return tuple(sorted(resolved))


def _entry_reached_by(entry: str, names: Iterable[JsonValue]) -> bool:
    """True when one of the dotted names reaches the entry.

    A `pkg.module:Name` entry is reached by exactly that name; a `pkg.module` entry by any
    name the module defines. Both ways an entry can be reached share this one match (AD-65),
    because an import's `reexport_chain` and a declared facade signature's `facade_types`
    carry the same dotted shape: neither can drift into a second reading of what an entry
    covers.
    """
    module, colon, name = entry.partition(":")
    target = f"{module}.{name}" if colon else ""
    return any(
        (item == target if colon else item.rpartition(".")[0] == module)
        for item in names
        if isinstance(item, str)
    )


def _facade_types(observation: Observation) -> tuple[str, ...]:
    """Every type a declared facade signature exposes, as the analyzer resolved it (AD-65).

    The analyzer writes `facade_types` on the facade function's own symbol record, using the
    resolution `boundary_types` (AD-63) already runs over the same annotations; reading it back
    here keeps one answer to "which type does this signature expose" instead of a second
    derivation that could disagree with the rule about the same position.
    """
    return tuple(
        name
        for record in observation.records("symbols") or ()
        if isinstance((types := record.data.get("facade_types")), tuple)
        for name in types
        if isinstance(name, str)
    )


def _entry_used(entry: str, records: list[RecordData], facade_types: tuple[str, ...]) -> bool:
    """Match one public entry's usage the way `_interface_allows` walks reexport_chain.

    Deliberately looser than the analyzer's runtime check: no `__all__` gate and no
    underscore rejection, since a public entry naming a private or unexported name is
    a rule violation already reported elsewhere, not an unused-entry drift signal.

    AD-65 adds the second way an entry is reached: a declared facade signature that names the
    type exposes it to every consumer of that signature, whether or not an import names it.
    AD-97: an import whose used names the scan cannot see may reach any name of its module, so
    it keeps a `module:Name` entry from reading unused on no evidence.
    """
    if _entry_reached_by(entry, facade_types):
        return True
    module, colon, _ = entry.partition(":")
    for data in records:
        chain = data.get("reexport_chain")
        if _entry_reached_by(entry, chain if isinstance(chain, tuple) else ()):
            return True
        if data.get("target_module") == module and (
            not colon or data.get("symbols_known") is False
        ):
            return True
    return False


def _imports_by_target(
    contract: ArchitectureContract, observation: Observation
) -> dict[str, list[RecordData]]:
    imports_by_target: dict[str, list[RecordData]] = {}
    for record in observation.records("imports") or ():
        source_module = record.data.get("source_module")
        target_module = record.data.get("target_module")
        if not isinstance(source_module, str) or not isinstance(target_module, str):
            continue
        source = contract.component_for(source_module)
        target = contract.component_for(target_module)
        if source is None or target is None or source == target:
            continue
        imports_by_target.setdefault(target.label, []).append(record.data)
    return imports_by_target


def _public_entry_diagnostics(
    index: int,
    component: ContractComponent,
    records: list[RecordData],
    modules: frozenset[str],
    facade_types: tuple[str, ...],
    resolved_public_entries: frozenset[tuple[str, str]],
) -> list[Diagnostic]:
    """Split an unused `public` entry by whether its module was ever scanned (AD-56).

    A module the scan never saw does not exist yet, `interface.missing`, whether that is a typo
    or a facade a refactoring has not built; one the scan saw but nothing reaches is
    `interface.unused`, same as before -- unless a declared facade signature exposes the type
    it names, which reaches it without an import (AD-65). A `pkg.module:Name` entry is judged
    by its module alone: `symbols` records only classes and functions, so absence from it
    would misreport a constant or type alias as missing. A used entry is checked against
    neither, exactly as before.
    """
    diagnostics = []
    for item, entry in enumerate(component.public or ()):
        if _entry_used(entry, records, facade_types):
            continue
        if _entry_module(entry) not in modules:
            diagnostics.append(
                _diagnostic(
                    "interface.missing",
                    f"/components/{index}/public/{item}",
                    entry,
                    "The public entry's module has not been scanned; it does not exist yet.",
                    "Build the module, correct a typo, or move the entry to planned "
                    "until it exists.",
                )
            )
        elif (component.label, entry) in resolved_public_entries:
            continue
        else:
            diagnostics.append(
                _diagnostic(
                    "interface.unused",
                    f"/components/{index}/public/{item}",
                    entry,
                    "No cross-component import and no declared facade signature "
                    "reaches this public entry.",
                    "Remove the entry or confirm another component should use it.",
                )
            )
    return diagnostics


def _planned_entry_diagnostics(
    index: int,
    component: ContractComponent,
    records: list[RecordData],
    modules: frozenset[str],
    facade_types: tuple[str, ...],
) -> list[Diagnostic]:
    """Flag a built `planned` entry once code actually reaches it (AD-56, #79).

    A built but unused module is still target work. Promotion is needed only when an import or
    declared facade signature reaches the planned entry.
    """
    return [
        _diagnostic(
            "interface.planned_built",
            f"/components/{index}/planned/{item}",
            entry,
            "The planned entry's module has been scanned; it is no longer planned.",
            "Move the entry to public and drop it from planned.",
        )
        for item, entry in enumerate(component.planned or ())
        if _entry_module(entry) in modules and _entry_used(entry, records, facade_types)
    ]


def _published_api_types(observation: Observation) -> dict[str, tuple[str, ...]]:
    """Each `declarations.public_api` entry mapped to the types its own signature exposes.

    Read off the `declared_public_api` records `public_api_exposed_types`
    (analyzer/embedded/violations.py, AD-70) already resolved -- `check` compares this published
    answer against the declared set instead of deriving a second one (AD-2's open payload, AD-4's
    one channel out of the analyzer).
    """
    types: dict[str, tuple[str, ...]] = {}
    for record in observation.records("declarations") or ():
        if record.kind != "declared_public_api":
            continue
        entry = text_value(record.data.get("qualified_name"))
        exposed = record.data.get("types")
        types[entry] = tuple(
            item
            for item in (exposed if isinstance(exposed, tuple) else ())
            if isinstance(item, str)
        )
    return types


def _public_api_entry_diagnostics(
    index: int,
    entry: str,
    modules: frozenset[str],
    exports: dict[str, frozenset[str]],
    exposed_types: dict[str, tuple[str, ...]],
    declared_api: frozenset[str],
) -> list[Diagnostic]:
    """One `declarations.public_api` entry's findings: existence (AD-66/AD-71) first, then
    AD-70's signature check once the entry is known to exist. Both read as `api_surface.missing`
    because either way a consumer was promised something this contract does not make good on.
    """
    module, _, name = entry.partition(":")
    pointer = f"/declarations/public_api/{index}"
    if module not in modules:
        return [
            _diagnostic(
                "api_surface.missing",
                pointer,
                entry,
                "The declared public API entry's module has not been scanned; "
                "it does not exist yet.",
                "Build the module, correct a typo, or remove the entry until it exists.",
            )
        ]
    if name and (exported := exports.get(module)) is not None and name not in exported:
        return [
            _diagnostic(
                "api_surface.missing",
                pointer,
                entry,
                "The module declares __all__ and the promised name is not in it.",
                "Export the name from the module, correct a typo, or remove the entry.",
            )
        ]
    return [
        _diagnostic(
            "api_surface.missing",
            pointer,
            entry,
            f"{entry} exposes {leaked.rpartition(':')[2]}, which declarations.public_api "
            "does not name.",
            f"Add {leaked} to declarations.public_api, or stop exposing it from this entry.",
        )
        for leaked in exposed_types.get(entry, ())
        if leaked not in declared_api
    ]


def public_api_diagnostics(
    contract: ArchitectureContract, observation: Observation
) -> tuple[Diagnostic, ...]:
    """Flag a `declarations.public_api` entry whose module the scan never saw (AD-66/AD-71), or
    whose signature exposes a type the declarations never name (AD-70).

    `public_api` names the surface a consumer *outside* this package may rely on, the case
    AD-9's component `public` never covered, so there is no cross-component import to make an
    `interface.unused` twin possible here (see `_public_api_entry_diagnostics`). AD-70 adds a
    second, independent signal once an entry is known to exist: a declared function's parameter
    and return types, and a declared class's own public attribute types, must themselves be
    named in `public_api` -- the generic form of the guard AD-58/AD-63 already hold a
    component's *internal* facade to, pointed here at the package's *external* one. The analyzer
    (`public_api_exposed_types`) resolves which types those are; this reads that answer rather
    than resolving annotations a second time.
    """
    declarations = contract.declarations or ContractDeclarations()
    modules = _scanned_modules(observation)
    exports = _literal_exports(observation)
    exposed_types = _published_api_types(observation)
    declared_api = frozenset(declarations.public_api)
    return tuple(
        diagnostic
        for index, entry in enumerate(declarations.public_api)
        for diagnostic in _public_api_entry_diagnostics(
            index, entry, modules, exports, exposed_types, declared_api
        )
    )


def _compatibility_import_diagnostics(
    shim: CompatibilityShim,
    pointer: str,
    all_exports: JsonValue,
    imports: tuple[Record, ...],
) -> tuple[Diagnostic, ...]:
    diagnostics: list[Diagnostic] = []
    imports_by_binding: dict[str, set[tuple[str, str | None]]] = {}
    for item in imports:
        binding = item.data.get("binding")
        target = item.data.get("target_module")
        if (
            item.data.get("source_module") == shim.module
            and isinstance(binding, str)
            and binding != "*"
            and isinstance(target, str)
        ):
            origin = item.data.get("origin_definition")
            if not isinstance(origin, str):
                origin = target if item.data.get("symbol") is None else None
            imports_by_binding.setdefault(binding, set()).add((target, origin))
    if not any(
        target == shim.target
        for imports_for_name in imports_by_binding.values()
        for target, _origin in imports_for_name
    ):
        diagnostics.append(
            _diagnostic(
                "compatibility.invalid",
                pointer,
                shim.module,
                "The compatibility module has no observed import of its declared target.",
                "Import the target module directly from the shim.",
            )
        )
    exported_names = (
        {name for name in all_exports if isinstance(name, str)}
        if isinstance(all_exports, tuple)
        else set()
    )
    for name in exported_names:
        imports_for_name = imports_by_binding.get(name, set())
        origins = {origin for _target, origin in imports_for_name}
        if (
            {target for target, _origin in imports_for_name} != {shim.target}
            or None in origins
            or len(origins) != 1
        ):
            diagnostics.append(
                _diagnostic(
                    "compatibility.invalid",
                    pointer,
                    shim.module,
                    "Every compatibility export must resolve only to the declared target.",
                    "Remove unrelated or ambiguous imports, or correct the declared target.",
                )
            )
            break
    if any(
        item.data.get("source_module") != shim.module
        and item.data.get("target_module") == shim.module
        for item in imports
    ):
        diagnostics.append(
            _diagnostic(
                "compatibility.invalid",
                pointer,
                shim.module,
                "Product code imports a compatibility module.",
                "Keep compatibility imports at the external boundary only.",
            )
        )
    return tuple(diagnostics)


def compatibility_diagnostics(
    contract: ArchitectureContract, observation: Observation
) -> tuple[Diagnostic, ...]:
    """Check declared shims from module and import facts already produced by the scan."""
    declarations = contract.declarations or ContractDeclarations()
    modules = {
        name: record.data
        for record in observation.records("modules") or ()
        if isinstance((name := record.data.get("qualified_name")), str)
    }
    imports = observation.records("imports") or ()
    diagnostics: list[Diagnostic] = []
    for index, shim in enumerate(declarations.compat):
        pointer = f"/declarations/compat/{index}"
        facts = modules.get(shim.module)
        if facts is None:
            diagnostics.append(
                _diagnostic(
                    "compatibility.invalid",
                    pointer,
                    shim.module,
                    "The declared compatibility module was not scanned.",
                    "Build the shim in the configured scan scope, or remove the declaration.",
                )
            )
            continue
        all_exports = facts.get("all_exports")
        if (
            facts.get("compatibility_logic_free") is not True
            or not isinstance(all_exports, tuple)
            or not all_exports
        ):
            diagnostics.append(
                _diagnostic(
                    "compatibility.invalid",
                    pointer,
                    shim.module,
                    "A compatibility module must contain only imports and a literal __all__.",
                    "Remove definitions and effectful statements, and declare a literal __all__.",
                )
            )
        if shim.target not in modules:
            diagnostics.append(
                _diagnostic(
                    "compatibility.invalid",
                    pointer,
                    shim.target,
                    "The declared compatibility target was not scanned.",
                    "Build the target module in the configured scan scope, or correct the "
                    "declaration.",
                )
            )
        diagnostics.extend(_compatibility_import_diagnostics(shim, pointer, all_exports, imports))
    return tuple(diagnostics)


def interface_diagnostics(
    contract: ArchitectureContract,
    observation: Observation,
    resolved_public_entries: frozenset[tuple[str, str]] = frozenset(),
) -> tuple[Diagnostic, ...]:
    """Require a declared interface for inbound imports and usage for declared entries.

    An entry is used when a cross-component import reaches it or when a declared facade
    signature exposes the type it names (AD-65): one notion of `public`, two ways of being
    reached.
    """
    if not any(isinstance(rule, InterfaceBoundaryRule) for rule in contract.rules):
        return ()
    imports_by_target = _imports_by_target(contract, observation)
    modules = _scanned_modules(observation)
    facade_types = _facade_types(observation)
    diagnostics = []
    for index, component in enumerate(contract.components):
        records = imports_by_target.get(component.label, [])
        if component.public is None:
            if records:
                diagnostics.append(
                    _diagnostic(
                        "interface.undeclared",
                        f"/components/{index}",
                        component.label,
                        "The component receives cross-component imports but declares "
                        "no public interface.",
                        "Declare the used modules or names in public.",
                    )
                )
        else:
            diagnostics.extend(
                _public_entry_diagnostics(
                    index,
                    component,
                    records,
                    modules,
                    facade_types,
                    resolved_public_entries,
                )
            )
        diagnostics.extend(
            _planned_entry_diagnostics(index, component, records, modules, facade_types)
        )
    return tuple(diagnostics)


_BUDGET_NOUNS: Final[dict[NameBudgetKind, str]] = {
    "facade_names": "facade",
    "coupling_names": "pair",
}


def interface_budget_diagnostics(
    results: tuple[InterfaceBudgetResult, ...], *, report_exceeded: bool
) -> tuple[Diagnostic, ...]:
    """AD-99: a budget over its target, or one the scan cannot count.

    A budget counts names, not which of them are too many, so an exceeded one lists them all.
    With a baseline its accepted names answer the target instead, the way AD-52 answers a
    violation, so only an uncountable budget is left to report there.
    """
    diagnostics = []
    for item in results:
        counted = (
            f"The {item.subject} {_BUDGET_NOUNS[item.budget]} counts "
            f"{'at least ' if item.uncounted else ''}{item.count} "
            f"{'name' if item.count == 1 else 'names'}"
        )
        if report_exceeded and item.over_target:
            diagnostics.append(
                _diagnostic(
                    "budget.exceeded",
                    item.pointer,
                    item.subject,
                    f"{counted}, {item.over_target} over max_names {item.max_names}: "
                    f"{', '.join(item.names)}.",
                    "Remove names until max_names holds; raising max_names widens the contract.",
                )
            )
        elif item.uncounted:
            diagnostics.append(
                _diagnostic(
                    "budget.unknown",
                    item.pointer,
                    item.subject,
                    f"{counted} against max_names {item.max_names}; not enumerated: "
                    f"{', '.join(item.uncounted)}.",
                    "Give the facade a literal __all__ or module:Name entries, and import the "
                    "used names explicitly.",
                )
            )
    return tuple(diagnostics)


def _name_budget_targets(declarations: ContractDeclarations) -> dict[str, int]:
    """Each declared facade and pair budget's `max_names`, by its baseline label (AD-99)."""
    return {
        **{
            budget_label("facade_names", item.subject): item.max_names
            for item in declarations.facade_budgets or ()
        },
        **{
            budget_label("coupling_names", item.subject): item.max_names
            for item in declarations.coupling_budgets or ()
        },
    }


def _name_budget(item: InterfaceBudgetResult) -> MeasurementBudget:
    """The accepted-name ratchet one measured budget writes to the baseline (AD-99)."""
    return MeasurementBudget(item.budget, item.count, item.subject, item.names)


def _compared_budgets(
    results: tuple[InterfaceBudgetResult, ...], accepted: tuple[MeasurementBudget, ...]
) -> tuple[InterfaceBudgetResult, ...]:
    """Each result with the names it adds to and drops from the baseline's accepted set."""
    held = {budget.label: budget for budget in accepted}
    compared = []
    for item in results:
        observed = _name_budget(item)
        before = held.get(observed.label)
        if before is None:
            compared.append(item)
            continue
        new, removed = name_drift(before, observed)
        compared.append(replace(item, new_names=new, removed_names=removed))
    return tuple(compared)


def rationale_diagnostics(contract: ArchitectureContract) -> tuple[Diagnostic, ...]:
    """Reject placeholder rationales and rationales that only repeat the rule."""
    diagnostics = []
    for index, rule in enumerate(contract.rules):
        rationale = rule.rationale.strip()
        code: DiagnosticCode
        if _REPEATED_RATIONALE.fullmatch(rationale):
            code = "rationale.repeated"
            claim = "The rationale repeats the forbidden dependency without explaining why."
        elif _PLACEHOLDER_RATIONALE.match(rationale):
            code = "rationale.placeholder"
            claim = "The rationale is a placeholder."
        else:
            continue
        diagnostics.append(
            _diagnostic(
                code,
                f"/rules/{index}/rationale",
                rule.id,
                claim,
                "Explain the architectural reason for this dependency boundary.",
            )
        )
    for index, component in enumerate(contract.components):
        for position, entry in enumerate(component.requires or ()):
            rationale = entry.rationale.strip()
            entry_code: DiagnosticCode
            if _REPEATED_REQUIRES.fullmatch(rationale):
                entry_code = "rationale.repeated"
                claim = "The rationale repeats the requires entry without explaining why."
            elif _PLACEHOLDER_RATIONALE.match(rationale):
                entry_code = "rationale.placeholder"
                claim = "The rationale is a placeholder."
            else:
                continue
            diagnostics.append(
                _diagnostic(
                    entry_code,
                    f"/components/{index}/requires/{position}/rationale",
                    f"{component.label} -> {entry.component}",
                    claim,
                    "Explain the architectural reason for this dependency boundary.",
                )
            )
    return tuple(diagnostics)


def _marked_bodies(content: str, marker: str) -> list[tuple[int, int]]:
    """Start and end of each Mermaid body that follows `marker`, before the next one.

    AD-57: the marker is a parameter, not a hardcoded constant, so `graph_diagnostics` and
    `rewrite_component_graph` read `COMPONENT_GRAPH_MARKER` and `TARGET_GRAPH_MARKER` through
    the one reader and can never disagree about where either marker's block starts and ends.
    """
    spans: list[tuple[int, int]] = []
    position = content.find(marker)
    while position != -1:
        following = content.find(marker, position + len(marker))
        limit = len(content) if following == -1 else following
        fence = content.find(_MERMAID_FENCE, position, limit)
        if fence != -1:
            start = fence + len(_MERMAID_FENCE)
            end = content.find("```", start, limit)
            spans.append((start, limit if end == -1 else end))
        position = following
    return spans


def _unwritable_line(body: str) -> str | None:
    """The first line of a marked block that is not a declaration, a `%%` comment or an edge.

    AD-46: a subgraph, a labeled edge or a style can depend on where an edge sits, so a rewrite
    that reorders the edges could change what the graph says; such a block is left to a human.
    """
    return next(
        (
            line.strip()
            for line in body.splitlines()
            if line.strip()
            and not _GRAPH_EDGE.fullmatch(line)
            and not _GRAPH_DECLARATION.fullmatch(line)
            and not _GRAPH_COMMENT.fullmatch(line)
        ),
        None,
    )


def mermaid_edges(edges: frozenset[tuple[str, str]]) -> str:
    """One sorted Mermaid line per component edge: what `init` and `--write-graph` write."""
    return "".join(f"    {source} --> {target}\n" for source, target in sorted(edges))


def rewrite_component_graph(
    documents: tuple[tuple[str, str], ...],
    observed_edges: frozenset[tuple[str, str]],
    target_edges: frozenset[tuple[str, str]],
) -> tuple[tuple[str, str], ...]:
    """Every marked graph's document with its edges replaced; empty if nothing is written.

    AD-46/AD-57: the two markers are rewritten independently, each only when the documents
    carry exactly one block for it; a marker absent everywhere is left alone, the way a page
    may carry either, both or neither, and one repeated is as ambiguous to rewrite as before -
    `graph.count` says so and this writes nothing for it either. The declaration and `%%`
    comments stay ahead of the edges, so a page's own `flowchart LR` survives, and a block
    without a declaration gets `init`'s; a block with any other line is not rewritten at all.
    Both markers may sit in the same document, which then comes back once with both edits.
    """
    edited: dict[str, str] = {}
    for marker, edges in (
        (COMPONENT_GRAPH_MARKER, observed_edges),
        (TARGET_GRAPH_MARKER, target_edges),
    ):
        current = {path: edited.get(path, content) for path, content in documents}
        blocks = [
            (path, span)
            for path, content in current.items()
            for span in _marked_bodies(content, marker)
        ]
        if len(blocks) != 1:
            continue
        path, (start, end) = blocks[0]
        content = current[path]
        body = content[start:end]
        if _unwritable_line(body) is not None:
            continue
        kept = [
            line for line in body.splitlines() if line.strip() and not _GRAPH_EDGE.fullmatch(line)
        ]
        if not any(_GRAPH_DECLARATION.fullmatch(line) for line in kept):
            kept.insert(0, "graph TD")
        written = (
            content[:start]
            + "".join(f"{line}\n" for line in kept)
            + mermaid_edges(edges)
            + content[end:]
        )
        if written != content:
            edited[path] = written
    return tuple(edited.items())


def _marker_diagnostics(
    marker: str,
    noun: str,
    claim_source: str,
    remedy_source: str,
    gone_label: str,
    new_label: str,
    edges: frozenset[tuple[str, str]],
    documents: tuple[tuple[str, str], ...],
    *,
    required: bool,
) -> tuple[Diagnostic, ...]:
    """One marker's graph.count/graph.drift findings; the subject always names the marker.

    AD-57: `required` is false for the target marker, so a page that draws none is silent -
    the target is optional, the way a page may carry either, both or neither - while the
    observed marker keeps AD-12's original rule, always exactly one.
    """
    graphs = [
        (path, content[start:end])
        for path, content in documents
        for start, end in _marked_bodies(content, marker)
    ]
    if not graphs and not required:
        return ()
    if len(graphs) != 1:
        return (
            _diagnostic(
                "graph.count",
                "/components",
                f"architecture {noun} graph",
                f"Expected one marked Mermaid {noun} graph, found {len(graphs)}.",
                f"Keep one graph after the archkeel-{noun}-graph marker in contract provenance.",
            ),
        )
    path, body = graphs[0]
    declared = frozenset(
        (match.group(1), match.group(2))
        for line in body.splitlines()
        if (match := _GRAPH_EDGE.fullmatch(line))
    )
    if declared == edges:
        return ()
    new_edges = ", ".join(f"{a}->{b}" for a, b in sorted(edges - declared)) or "none"
    gone_edges = ", ".join(f"{a}->{b}" for a, b in sorted(declared - edges)) or "none"
    unwritable = _unwritable_line(body)
    return (
        _diagnostic(
            "graph.drift",
            "/components",
            f"{path} ({noun} graph)",
            f"The marked {noun} graph differs from {claim_source}; "
            f"{gone_label}: {gone_edges}; {new_label}: {new_edges}.",
            "Run archkeel validate --write-graph to regenerate the marked Mermaid graph "
            f"from {remedy_source}."
            if unwritable is None
            else f"Edit the marked graph's edges by hand: it holds `{unwritable}`, structure "
            "archkeel validate --write-graph does not rewrite.",
        ),
    )


def graph_diagnostics(
    contract: ArchitectureContract,
    observation: Observation,
    documents: tuple[tuple[str, str], ...],
) -> tuple[Diagnostic, ...]:
    """Require the observed marker always, and the target marker whenever a page draws one.

    AD-57: `<!-- archkeel-target-graph -->` is compared against `target_component_edges`, the
    pairs the contract permits, beside `<!-- archkeel-component-graph -->`'s unchanged
    comparison against observed imports; the two are independent, so one may drift while the
    other passes, and each diagnostic's subject names its own marker.
    """
    (
        observed_marker,
        observed_noun,
        observed_claim,
        observed_remedy,
        observed_gone,
        observed_new,
    ) = _GRAPH_MARKERS[0]
    target_marker, target_noun, target_claim, target_remedy, target_gone, target_new = (
        _GRAPH_MARKERS[1]
    )
    return (
        *_marker_diagnostics(
            observed_marker,
            observed_noun,
            observed_claim,
            observed_remedy,
            observed_gone,
            observed_new,
            observed_component_edges(contract, observation),
            documents,
            required=True,
        ),
        *_marker_diagnostics(
            target_marker,
            target_noun,
            target_claim,
            target_remedy,
            target_gone,
            target_new,
            target_component_edges(contract),
            documents,
            required=False,
        ),
    )


def _sorted(diagnostics: list[Diagnostic]) -> tuple[Diagnostic, ...]:
    return tuple(
        sorted(
            diagnostics,
            key=lambda item: (item.pointer or "", item.subject, item.unknown_claim, item.remedy),
        )
    )


def _provenance(contract: ArchitectureContract) -> tuple[tuple[str, tuple[str, ...]], ...]:
    declarations = contract.declarations or ContractDeclarations()
    return (
        *(
            (f"/components/{index}/provenance", item.provenance)
            for index, item in enumerate(contract.components)
        ),
        *(
            (f"/rules/{index}/provenance", item.provenance)
            for index, item in enumerate(contract.rules)
        ),
        *(
            (f"/declarations/capabilities/{index}/provenance", item.provenance)
            for index, item in enumerate(declarations.capabilities)
        ),
        *(
            (f"/declarations/review_scopes/{index}/provenance", item.provenance)
            for index, item in enumerate(declarations.review_scopes)
        ),
        *(
            (f"/declarations/public_commands/{index}/provenance", item.provenance)
            for index, item in enumerate(declarations.public_commands)
        ),
        *(
            (f"/declarations/paths/{index}/provenance", item.provenance)
            for index, item in enumerate(declarations.paths)
        ),
        *(
            (f"/declarations/spot_owners/{index}/provenance", item.provenance)
            for index, item in enumerate(declarations.spot_owners)
        ),
        *(
            (f"/declarations/facade_budgets/{index}/provenance", item.provenance)
            for index, item in enumerate(declarations.facade_budgets or ())
        ),
        *(
            (f"/declarations/coupling_budgets/{index}/provenance", item.provenance)
            for index, item in enumerate(declarations.coupling_budgets or ())
        ),
        ("/declarations/public_api_provenance", declarations.public_api_provenance),
        ("/declarations/context_roots_provenance", declarations.context_roots_provenance),
    )


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
                    "reference.public_owner",
                    pointer,
                    entry,
                    "The public entry's module is not owned by this component.",
                    "Move the entry to its owning component or correct the module.",
                )
            )
        if name.startswith("_"):
            diagnostics.append(
                _diagnostic(
                    "reference.public_underscore",
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
            "reference.namespace",
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
    for pointer, values in _provenance(contract):
        for index, value in enumerate(values):
            if repository_file(repository, value) is None:
                diagnostics.append(
                    _diagnostic(
                        "reference.provenance",
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
                            "reference.package_unscanned",
                            f"/components/{component_index}/packages/{package_index}",
                            package,
                            "The component package has no scanned Python module.",
                            "Correct the package or include it in scan.roots.",
                        )
                    )
    return _sorted(diagnostics)


def _inside_pointers(contract: ArchitectureContract, observation: Observation) -> dict[str, str]:
    """Pointer per record an inside declares: the component whose `inside` names it (AD-36).

    Such a rule is in no `rules` array of this contract, so a reader sent to `/rules/<n>` would
    be shown an unrelated decision; the component is where the level, and its contract, begin.
    """
    positions = {
        component.label: index
        for index, component in enumerate(contract.components)
        if component.inside is not None
    }
    declarations = observation.records("declarations") or ()
    inside_parents = {
        f"{parent}:{record.title}": parent
        for record in declarations
        if record.kind == "inside_component_responsibility"
        and record.data.get("inside") is not None
        and (parent := text_value(record.data.get("parent_id"))) is not None
    }
    pointers: dict[str, str] = {}
    for record in declarations:
        parent = text_value(record.data.get("parent_id"))
        if parent is None:
            continue
        visited: set[str] = set()
        while parent not in positions:
            if parent in visited:
                break
            visited.add(parent)
            owner = inside_parents.get(parent)
            if owner is None:
                break
            parent = owner
        if parent in positions:
            pointers[record.id] = f"/components/{positions[parent]}/inside"
    return pointers


def observation_diagnostics(
    contract: ArchitectureContract,
    observation: Observation,
    documents: tuple[tuple[str, str], ...],
    *,
    report_violations: bool = True,
    resolved_public_entries: frozenset[tuple[str, str]] = frozenset(),
) -> tuple[Diagnostic, ...]:
    """Validate rules, closed-world coverage and architecture documentation.

    AD-52: a run carrying a baseline answers the violations there instead, so it asks for no
    `rule.violated` diagnostic here; every other finding is unchanged and still exits 2.
    """
    rule_index = {rule.id: index for index, rule in enumerate(contract.rules)}
    inside_pointers = _inside_pointers(contract, observation)
    diagnostics = [
        *closed_world_diagnostics(contract, observation),
        *interface_diagnostics(contract, observation, resolved_public_entries),
        *public_api_diagnostics(contract, observation),
        *compatibility_diagnostics(contract, observation),
        *rationale_diagnostics(contract),
        *graph_diagnostics(contract, observation, documents),
    ]
    reported = (observation.records("violations") or ()) if report_violations else ()
    for record in reported:
        rule_id = record.rule_ids[0] if record.rule_ids else record.id
        index = rule_index.get(rule_id)
        diagnostics.append(
            _diagnostic(
                "rule.violated",
                f"/rules/{index}" if index is not None else inside_pointers.get(rule_id, ""),
                rule_id,
                f"The observed code violates the declared rule: {record.title}",
                "Change the code or amend the contract with owner approval.",
            )
        )
    return _sorted(diagnostics)


def invalid_result(subject: str, error: Exception, pointer: str = "") -> RunResult:
    return RunResult(
        "validate",
        2,
        diagnostics=(
            _diagnostic(
                "contract.invalid",
                pointer,
                subject,
                f"The architecture contract cannot be validated: {error}",
                "Correct the input and run archkeel validate again.",
            ),
        ),
    )


def _inside_public(inner: ArchitectureContract) -> frozenset[str]:
    """The inside's public surface: what its own components offer, taken together."""
    return frozenset(entry for item in inner.components for entry in (item.public or ()))


def _forbidden_targets(
    contract: ArchitectureContract, packages: tuple[str, ...]
) -> list[tuple[str, str]]:
    """Each rule id and target the level above forbids a component, by any of its packages.

    The id travels with the target because the diagnostic exists to point at a decision, and
    a reader cannot find the decision from the target alone.
    """
    return [
        (rule.id, rule.target)
        for rule in contract.rules
        if isinstance(rule, ForbiddenDependencyRule)
        and any(in_scope(rule.source, package) for package in packages)
    ]


def _denied_by_absence(
    contract: ArchitectureContract, label: str, required: frozenset[str], target: str
) -> str | None:
    """The `complete_requires` rule refusing an edge the component never asked for (AD-32).

    Absence decides only where such a rule is in force, and only for a target another
    component owns: a target inside the component itself is no component edge at all, and one
    no component owns belongs to the external scope rules instead. Without this, a level whose
    pairs are decided by absence - which is how this repository decides them - would let its
    inside grant anything, because there is no `forbidden_dependency` left to contradict.
    """
    rule = next((item for item in contract.rules if isinstance(item, CompleteRequiresRule)), None)
    if rule is None:
        return None
    owner = contract.component_for(target)
    if owner is None or owner.label == label or owner.label in required:
        return None
    return rule.id


def _inside_source_domain_diagnostics(
    pointer: str, component: ContractComponent, inner: ArchitectureContract
) -> list[Diagnostic]:
    """Reject nested physical claims outside the component holding the inside."""
    return [
        _diagnostic(
            "contract.invalid",
            pointer,
            package,
            f"The inside claims {package}, outside {component.label}'s physical packages.",
            "Keep every inside component package within the parent component's packages.",
        )
        for child in inner.components
        for package in child.packages
        if not any(in_scope(package, parent) for parent in component.packages)
    ]


def inside_diagnostics(
    root: Path,
    contract: ArchitectureContract,
    config: ScanConfig,
    tree: InsideContractTree | None = None,
) -> tuple[Diagnostic, ...]:
    """AD-20: hold a component and the contract describing its inside to each other.

    Two checks: the levels must agree on the component's public surface, and the inside must
    not grant itself what the level above denies the component. Grants are read from the
    inside's `allowed_dependency` rules; an `external_dependency_scope` there is not yet
    compared, which stays a blind spot. AD-99 adds that the inside declares no budget.
    """
    diagnostics: list[Diagnostic] = []
    loaded = tree or _inside_contract_tree(root, config.contract, contract)
    if loaded is None:
        return ()
    for issue in loaded.issues:
        diagnostics.append(
            _diagnostic(
                "contract.invalid",
                issue.pointer,
                issue.path,
                f"The contract describing this inside cannot be loaded: {issue.reason}",
                "Repair the repository-relative contract reference.",
            )
        )
    for mount in loaded.mounts:
        inner = mount.contract
        parent = mount.parent
        pointer = mount.pointer
        for path_pointer, values in _provenance(inner):
            for index, value in enumerate(values):
                if repository_file(root.resolve(), value) is None:
                    diagnostics.append(
                        _diagnostic(
                            "reference.provenance",
                            f"{pointer}{path_pointer}/{index}",
                            value,
                            "The provenance file is missing or outside the repository.",
                            "Reference an existing repository-relative evidence file.",
                        )
                    )
        diagnostics.extend(_inside_source_domain_diagnostics(pointer, parent, inner))
        declared = frozenset(parent.public or ())
        inside = _inside_public(inner)
        if declared != inside:
            diagnostics.append(
                _diagnostic(
                    "inside.public_mismatch",
                    pointer,
                    mount.parent_id,
                    f"The level above declares {sorted(declared)} public for this component "
                    f"while its inside declares {sorted(inside)}.",
                    "Declare one public surface and repeat it in both contracts.",
                )
            )
        denied = _forbidden_targets(mount.parent_contract, parent.packages)
        required = frozenset(entry.component for entry in parent.requires or ())
        for rule in inner.rules:
            if not isinstance(rule, AllowedDependencyRule):
                continue
            blocked = [rule_id for rule_id, value in denied if in_scope(rule.target, value)]
            absent = _denied_by_absence(mount.parent_contract, parent.label, required, rule.target)
            if absent is not None:
                blocked.append(absent)
            if blocked:
                diagnostics.append(
                    _diagnostic(
                        "inside.forbidden_import",
                        pointer,
                        f"{mount.parent_id} -> {rule.target}",
                        f"The inside allows {rule.target}, which {', '.join(sorted(blocked))} "
                        f"forbids {mount.parent_id} at the level above.",
                        "Remove the grant inside, or decide the pair differently above.",
                    )
                )
    return _sorted(diagnostics)


def _repository_diagnostics(
    root: Path,
    config: ScanConfig,
    contract: ArchitectureContract,
    observation: Observation,
    write_graph: bool,
    report_violations: bool,
    resolved_public_entries: frozenset[tuple[str, str]] = frozenset(),
    inside_tree: InsideContractTree | None = None,
) -> tuple[list[Diagnostic], tuple[tuple[str, str], ...]]:
    """Every diagnostic a complete observation adds, once the contract's references hold.

    AD-46/AD-57: `write_graph` rewrites both marked graphs first, so the diagnostics judge the
    pages as they will be written, and every rewritten page comes back with its path.
    """
    # The page is written back as UTF-8, so it is read as UTF-8 whatever the locale says.
    documents = tuple(
        (path, (root / path).read_text(encoding="utf-8"))
        for path in contract_provenance_paths(contract)
    )
    edits = (
        rewrite_component_graph(
            documents,
            observed_component_edges(contract, observation),
            target_component_edges(contract),
        )
        if write_graph
        else ()
    )
    if edits:
        written = dict(edits)
        documents = tuple((path, written.get(path, text)) for path, text in documents)
    return [
        *reference_diagnostics(root, config, contract, observation),
        *observation_diagnostics(
            contract,
            observation,
            documents,
            report_violations=report_violations,
            resolved_public_entries=resolved_public_entries,
        ),
        *inside_diagnostics(root, contract, config, inside_tree),
    ], edits


def _observed_result(
    observation: Observation,
    diagnostics: list[Diagnostic],
    failures: tuple[str, ...] = (),
    *,
    baseline_new: int | None = None,
    baseline_resolved: int | None = None,
    interface_budgets: tuple[InterfaceBudgetResult, ...] | None = None,
) -> RunResult:
    """The validate result once a complete observation has produced its diagnostics.

    AD-52: a baseline's own findings arrive as `failures` and exit 1, which keeps a
    diagnostic and exit 2 meaning what they always meant - nothing could be judged.
    """
    try:
        measurements, declared = inspect_observation(observation)
    except ValueError as error:
        diagnostics.append(
            _diagnostic(
                "observation.incomplete",
                "",
                "observation",
                f"The observation is incomplete: {error}",
                "Repair the analyzer evidence and retry.",
            )
        )
        measurements = None
        declared = "FAIL"
    decisions = open_decisions(observation)
    counts = agent_decisions(observation)
    # AD-51: a rejected run is where the breakdown is read, so it carries it too.
    counted = violation_counts(observation)
    if diagnostics:
        return RunResult(
            "validate",
            2,
            diagnostics=_sorted(diagnostics),
            coverage=observation.coverage,
            python_version=observation.python_version,
            open_decisions=decisions,
            agent_decisions=counts,
            violations_by_rule=counted.by_rule,
            violations_by_component_pair=counted.by_component_pair,
            baseline_new=baseline_new,
            baseline_resolved=baseline_resolved,
            interface_budgets=interface_budgets,
        )
    return RunResult(
        "validate",
        1 if failures else 0,
        observation_complete="PASS",
        declared_rules=declared,
        expectation_fulfilled="n/a",
        coverage=observation.coverage,
        python_version=observation.python_version,
        measurements=measurements,
        failures=failures,
        baseline_new=baseline_new,
        baseline_resolved=baseline_resolved,
        open_decisions=decisions,
        agent_decisions=counts,
        claims=review_claims(observation),
        violations_by_rule=counted.by_rule,
        violations_by_component_pair=counted.by_component_pair,
        interface_budgets=interface_budgets,
    )


_UNCOMPARED = "the --against revision's calls could not be compared, so no call site is named"
_ONE_SIDED = (
    "added calls in files only the working tree holds (git-ignored, inside a submodule, or "
    "export-ignore at the --against revision) are not named"
)
_NOTHING_DIFFERS = (
    "no unresolved call differs from the --against revision; the accepted value does not match "
    "that revision's code"
)


def _unresolved_calls_since(
    root: Path, config: ScanConfig, analyzer: Analyzer, against: str, observation: Observation
) -> tuple[tuple[UnresolvedCallChange, ...] | None, str | None]:
    """AD-100: the unresolved calls whose count differs from the code at `against`, and why
    any of them goes unnamed.

    None when that revision's source cannot be observed completely: the sites explain a
    finding, they never decide one. The revision is scanned under its own contract, the way
    `check` scans its accepted commit, so a rule naming a module only the new code has cannot
    leave the old scan without subjects, and a removed call names the component it had then.
    """
    try:
        observed = observe_revision(analyzer, root, against, config, declared_at=against)
        if observed.diagnostics or observed.observation is None:
            return None, _UNCOMPARED
        changes = unresolved_call_changes(observed.observation, observation)
        one_sided = _one_sided_paths(root, config, observed.observation, changes)
    except (GitError, SnapshotError, RatchetError):
        return None, _UNCOMPARED
    named = tuple(
        item for item in changes if item.change == "removed" or item.path not in one_sided
    )
    if len(named) < len(changes):
        return named, _ONE_SIDED
    return named, None if named else _NOTHING_DIFFERS


def _one_sided_paths(
    root: Path,
    config: ScanConfig,
    before: Observation,
    changes: tuple[UnresolvedCallChange, ...],
) -> frozenset[str]:
    """AD-100: the added rows' files only the working-tree side can hold.

    The working tree is read from disk, the revision from its `git archive` snapshot. A file the
    snapshot holds is on both sides and always compared, and so is a removed row's. Of the rest,
    a file outside Git's view of the working tree (ignored, or inside a submodule) is never
    archived, and one the revision tracks was left out by its own `export-ignore`.
    """
    archived = {text_value(record.data.get("file")) for record in before.records("modules") or ()}
    added = frozenset(item.path for item in changes if item.change == "added") - archived
    if not added:
        return frozenset()
    tracked = tracked_paths(root, before.source.git_head, config.roots)
    visible = working_tree_paths(root, config.roots)
    return frozenset(path for path in added if path not in visible or path in tracked)


def _calls_unresolved(budgets: tuple[MeasurementBudget, ...]) -> int | None:
    return next((item.value for item in budgets if item.name == "calls_unresolved"), None)


_BASELINE_WRITE = (
    "Correct the baseline, or write it with archkeel validate --baseline <path> --write-baseline."
)
# AD-106: a write reads an existing file first, so advising one for an unreadable file loops.
_BASELINE_CORRECT = (
    "Correct the baseline file by hand; a write reads it first and stops on the same error."
)
# AD-103: a path outside the root is refused before any read or write.
_BASELINE_INSIDE_ROOT = "Pass a --baseline path inside --root, relative to it or absolute."


def _baseline_invalid(path: Path, error: Exception, remedy: str) -> RunResult:
    return RunResult(
        "validate",
        2,
        diagnostics=(
            _diagnostic(
                "baseline.invalid",
                "",
                str(path),
                f"The validation baseline cannot be read: {error}",
                remedy,
            ),
        ),
    )


def _budget_baseline_missing() -> RunResult:
    return RunResult(
        "validate",
        2,
        diagnostics=(
            _diagnostic(
                "baseline.invalid",
                "/declarations/measurement_budgets",
                "measurement_budgets",
                "The contract selects measurement budgets but --baseline was not supplied.",
                "Run validate with --baseline <path>; add --write-baseline to record the "
                "current values.",
            ),
        ),
    )


def _against_invalid(against: str, error: Exception) -> RunResult:
    return RunResult(
        "validate",
        2,
        diagnostics=(
            _diagnostic(
                "against.invalid",
                "",
                against,
                f"The compared revision cannot be read: {error}",
                "Supply a Git revision this repository can resolve, with a valid contract at "
                "its configured path.",
            ),
        ),
    )


def _amendment_invalid(path: Path, error: Exception) -> RunResult:
    return RunResult(
        "validate",
        2,
        diagnostics=(
            _diagnostic(
                "amendment.invalid",
                "",
                str(path),
                f"The contract-widening amendment cannot be read: {error}",
                "Correct the amendment, or write it with archkeel validate --against <ref> "
                "--amendment <path> --write-amendment --decided-by <who> --rationale <why>.",
            ),
        ),
    )


def _parse_contract_or_invalid(root: Path, config: ScanConfig) -> ArchitectureContract | RunResult:
    """The parsed contract, or the exit-2 result naming why it could not be read."""
    try:
        return parse_contract(decode_json((root / config.contract).read_bytes()))
    except ContractVersionError as error:
        return RunResult(
            "validate",
            2,
            diagnostics=(
                _diagnostic(
                    "contract.schema_version",
                    "/schema_version",
                    config.contract,
                    f"Contract schema {error.actual} cannot be validated as "
                    f"{CONTRACT_SCHEMA_VERSION}.",
                    "Migrate the contract using docs/rules.md#migrating-from-1-1-0.",
                ),
            ),
        )
    except (OSError, ValueError) as error:
        return invalid_result(config.contract, error)


def _observed_or_invalid(
    root: Path,
    config: ScanConfig,
    analyzer: Analyzer,
    contract: ArchitectureContract,
) -> Observation | RunResult:
    """The complete observation, or the exit-2 result naming what analyzer evidence is missing."""
    observed = observe_repository(root, config, analyzer)
    observation = observed.observation
    if observed.diagnostics or observation is None:
        if observation is not None and any(
            item.kind == "inside_contract_incomplete"
            for item in observation.records("unknowns") or ()
        ):
            extra, _ = _repository_diagnostics(
                root,
                config,
                contract,
                observation,
                write_graph=False,
                report_violations=True,
            )
            diagnostics = [
                *(replace(item, pointer=item.pointer or "") for item in observed.diagnostics),
                *extra,
            ]
            return RunResult(
                "validate",
                2,
                diagnostics=tuple(dict.fromkeys(diagnostics)),
                coverage=observed.coverage,
                python_version=observation.python_version,
            )
        return RunResult(
            "validate",
            2,
            diagnostics=tuple(
                replace(item, pointer=item.pointer or "") for item in observed.diagnostics
            ),
            coverage=observed.coverage,
        )
    return observation


@dataclass(frozen=True, slots=True)
class _Introduced:
    """AD-104: the `--against` revision holds no contract at `path`, its repository path."""

    path: str


@dataclass(frozen=True, slots=True)
class _AgainstContext:
    """Everything `--against` and `--amendment` resolve to, threaded through one run (AD-61)."""

    against: str | None
    contract: ArchitectureContract | _Introduced | None
    # None: nothing at `against` to compare the baseline with (AD-104).
    baseline: tuple[KnownViolation, ...] | None
    budgets: tuple[MeasurementBudget, ...]
    amendment: Path | None
    write_amendment: bool
    parsed_amendment: Amendment | None
    decided_by: str | None
    rationale: str | None
    config: ScanConfig | None
    tree_digest: str | None = None


def _revision_contract_tree(root: Path, revision: str, path: str) -> InsideContractTree:
    """Resolve one revision's root and explicit inside declarations from Git blobs."""
    contract = parse_contract(decode_json(read_blob(root, revision, path)))

    def read_inside(reference: str) -> tuple[bytes, str]:
        try:
            return read_blob(root, revision, reference), reference
        except GitError as error:
            raise ValueError(str(error)) from error

    tree = load_inside_contract_tree(
        path,
        contract,
        contract_digest(contract),
        path,
        read_inside,
    )
    if tree.issues:
        issue = tree.issues[0]
        raise ValueError(f"inside {issue.path!r}: {issue.reason}")
    return tree


def _resolve_against_context(
    root: Path,
    config: ScanConfig,
    against: str | None,
    baseline: Path | None,
    amendment: Path | None,
    write_amendment: bool,
    decided_by: str | None,
    rationale: str | None,
    against_config: ScanConfig | None,
) -> tuple[_AgainstContext, RunResult | None]:
    """Resolve revision inputs without treating absent measurement budgets as zero."""
    empty = _AgainstContext(
        against,
        None,
        (),
        (),
        amendment,
        write_amendment,
        None,
        decided_by,
        rationale,
        against_config,
    )
    if against is None:
        return empty, None
    parsed_amendment, amendment_error = _resolve_amendment(amendment, write_amendment)
    against_contract_path = (
        against_config.contract if against_config is not None else config.contract
    )
    try:
        tree = _revision_contract_tree(root, against, against_contract_path)
        against_contract: ArchitectureContract | _Introduced = tree.comparison_contract
        before_tree_digest: str | None = tree.comparison_digest
    except MissingBlobError as error:
        against_contract = _Introduced(error.path)
        before_tree_digest = None
    except (GitError, ValueError) as error:
        return empty, _against_invalid(against, error)
    try:
        against_baseline, against_budgets, missing_budgets = _against_baseline_state(
            root, against, baseline, against_contract
        )
    except (GitError, ValueError) as error:
        return empty, _against_invalid(against, error)
    if missing_budgets:
        missing = ", ".join(missing_budgets)
        return empty, _against_invalid(
            against,
            ValueError(f"measurement budget values are missing for: {missing}"),
        )
    context = _AgainstContext(
        against,
        against_contract,
        against_baseline,
        against_budgets,
        amendment,
        write_amendment,
        parsed_amendment,
        decided_by,
        rationale,
        against_config,
        before_tree_digest,
    )
    return context, amendment_error


def _against_baseline_state(
    root: Path,
    against: str,
    baseline: Path | None,
    contract: ArchitectureContract | _Introduced,
) -> tuple[
    tuple[KnownViolation, ...] | None,
    tuple[MeasurementBudget, ...],
    list[str],
]:
    # Without the contract every entry of a baseline the revision lacks too would repeat the
    # introduction, so that baseline is not compared rather than read as no known debt.
    violations: tuple[KnownViolation, ...] | None = (
        None if isinstance(contract, _Introduced) else ()
    )
    budgets: tuple[MeasurementBudget, ...] = ()
    baseline_at = _baseline_at(root, baseline)
    prior = None if baseline_at is None else _prior_baseline(root, against, baseline_at)
    if prior is not None:
        violations, budgets = prior.violations, prior.budgets
    declarations = contract.declarations if isinstance(contract, ArchitectureContract) else None
    declared: set[str] = set()
    for item in (declarations or ContractDeclarations()).measurement_budgets:
        declared.add(item.name)
    known: set[str] = set()
    for budget in budgets:
        known.add(budget.label)
    missing = sorted(declared - known)
    return violations, budgets, missing


def _prior_baseline(root: Path, against: str, path: str) -> ValidationBaseline | None:
    """The baseline `against` holds at `path`, or None where it holds none; one it holds but
    cannot hand over raises GitError or ValueError."""
    try:
        payload = read_blob(root, against, path)
    except MissingBlobError:
        return None
    return parse_validation_baseline(decode_json(payload))


def _resolve_amendment(
    amendment: Path | None, write_amendment: bool
) -> tuple[Amendment | None, RunResult | None]:
    if amendment is None or write_amendment:
        return None, None
    try:
        return parse_amendment(decode_json(amendment.read_bytes())), None
    except (OSError, ValueError) as error:
        return None, _amendment_invalid(amendment, error)


def _before_digest(
    contract: ArchitectureContract | _Introduced, tree_digest: str | None = None
) -> str:
    """The digest an amendment binds for the `--against` side (AD-61, AD-104)."""
    if isinstance(contract, _Introduced):
        return absent_contract_digest(contract.path)
    return tree_digest or contract_digest(contract)


def _cycle_rule_ids(contract: ArchitectureContract) -> frozenset[str]:
    """The rules whose violation subjects are one SCC's members, so a subset contracts (AD-98)."""
    return frozenset(rule.id for rule in contract.rules if isinstance(rule, NoComponentCyclesRule))


def _rename_since(
    ctx: _AgainstContext,
    contract: ArchitectureContract,
    observation: Observation,
    root: Path,
    config: ScanConfig,
    analyzer: Analyzer,
) -> Renamed | None:
    """AD-105: the compared revision under a rename supported by both physical layouts."""
    if (
        ctx.against is None
        or not isinstance(ctx.contract, ArchitectureContract)
        or ctx.config is None
    ):
        return None
    if ctx.contract.components == contract.components:
        return None
    historical_config = ctx.config
    current_layouts = module_layouts(observation)
    historical_layouts = current_layouts
    historical_scanned = False
    if historical_config.language != config.language:
        return None
    if config.language == "python":
        try:
            historical = observe_revision(
                analyzer, root, ctx.against, historical_config, declared_at=ctx.against
            )
        except (GitError, OSError, SnapshotError, ValueError):
            return None
        if historical.diagnostics or historical.observation is None:
            return None
        historical_layouts = module_layouts(historical.observation)
        historical_scanned = True
    elif historical_config.roots != config.roots:
        return None
    layouts = current_layouts | historical_layouts
    recognised = renames_since(
        ctx.contract,
        contract,
        violations=ctx.baseline or (),
        budgets=ctx.budgets,
        observed=observed_names(observation),
        layouts=layouts,
    )
    historical_renames = renames_since(
        ctx.contract,
        contract,
        violations=ctx.baseline or (),
        budgets=ctx.budgets,
        observed=observed_names(observation),
        layouts=historical_layouts,
    )
    return next(
        (
            item
            for item in recognised
            if not historical_scanned
            or any(previous.prefixes == item.prefixes for previous in historical_renames)
            if not any(_left_behind(root, directory) for directory in item.directories)
        ),
        None,
    )


def _left_behind(root: Path, directory: str) -> bool:
    """AD-105: whether a file lies at or below `directory`, or beside it as `directory.*`, where
    an old prefix's code lived: scanned under a new name or not, it is code left behind. A file
    in `__pycache__` is none, since Python loads one only beside its source."""
    base: Path = root / directory
    parent: Path = base.parent
    files = [base, *base.rglob("*"), *parent.glob(f"{base.name}.*")]
    return any(_code_file(root, path) for path in files)


def _code_file(root: Path, path: Path) -> bool:
    relative: Path = path.relative_to(root)
    return path.is_file() and "__pycache__" not in relative.parts


def _widening_failures(
    ctx: _AgainstContext,
    contract: ArchitectureContract,
    rename: Renamed | None,
    baseline: Path | None,
    after_baseline: tuple[KnownViolation, ...],
    after_budgets: tuple[MeasurementBudget, ...],
    cycle_rules: frozenset[str],
    after_digest: str,
) -> tuple[str, ...]:
    """Every unamended widening from `ctx.contract` to `contract` (AD-61, #11).

    A recognised rename is applied to the old side first (AD-105), so only what it does not
    explain is compared, and a widening beside it is still reported.
    """
    if ctx.against is None or ctx.contract is None:
        return ()
    violations, budgets = ctx.baseline, ctx.budgets
    if isinstance(ctx.contract, _Introduced):
        # AD-104: nothing at the revision to compare, so the whole contract is one widening, and
        # no rename applies to it (AD-105).
        findings = [f"contract introduced: {ctx.contract.path} does not exist at {ctx.against}"]
        targets: dict[str, int] = {}
    else:
        before = ctx.contract
        if rename is not None:
            before, budgets = rename.contract, rename.budgets
            violations = None if violations is None else rename.violations
        findings = list(contract_widenings(before, contract))
        targets = _name_budget_targets(before.declarations or ContractDeclarations())
    if baseline is not None and violations is not None:
        findings += baseline_widenings(violations, after_baseline, cycle_rules=cycle_rules)
        findings += measurement_budget_widenings(budgets, after_budgets, targets)
    amended = ctx.write_amendment or (
        ctx.parsed_amendment is not None
        and verify_amendment(
            ctx.parsed_amendment,
            before_digest=_before_digest(ctx.contract, ctx.tree_digest),
            after_digest=after_digest,
        )
    )
    return tuple(findings) if findings and not amended else ()


def _artifact_files(
    *,
    write_baseline: bool,
    baseline: Path | None,
    violations: tuple[KnownViolation, ...],
    budgets: tuple[MeasurementBudget, ...],
    against: _AgainstContext,
    edits: tuple[tuple[str, str], ...],
    exit_code: int,
    current_digest: str,
) -> tuple[dict[str, bytes], str | None]:
    """Every file this run writes, and the last one written, as the result's `artifact`.

    AD-46/AD-57: every rewritten graph page is written before the diagnostics judge it,
    whatever they say; a baseline or an amendment records what a run could judge, so exit 2
    writes neither.
    """
    files: dict[str, bytes] = {}
    artifact: str | None = None
    if write_baseline and baseline is not None and exit_code != 2:
        artifact = str(baseline)
        files[artifact] = baseline_bytes(violations, budgets)
    if (
        against.write_amendment
        and against.contract is not None
        and against.amendment is not None
        and exit_code != 2
    ):
        artifact = str(against.amendment)
        files[artifact] = amendment_bytes(
            Amendment(
                _before_digest(against.contract, against.tree_digest),
                current_digest,
                against.decided_by or "",
                against.rationale or "",
            )
        )
    for page, written in edits:
        artifact = page
        files[page] = written.encode()
    return files, artifact


def _baseline_at(root: Path, baseline: Path | None) -> str | None:
    """`--baseline`'s repository-relative path, or None without one; `_root_path` keeps it
    under `root`, and any other path raises instead of leaving `--against` unchecked (AD-103)."""
    if baseline is None:
        return None
    return baseline.resolve().relative_to(root.resolve()).as_posix()


def _root_path(root: Path, path: Path) -> Path:
    """`path` as validate reads and writes it: relative to `root`, or absolute, and resolved,
    symlinks included, inside `root` (AD-103).

    A relative `path` that, read from a working directory outside `root`, leads into it repeats
    the root's own prefix (`--root mobile --baseline mobile/b.json`). While nothing exists at
    the root-relative path, it is refused: never read or written one directory too deep.
    """
    repository: Path = root.resolve()
    named: Path = repository / path
    target: Path = named.resolve()
    if repository not in target.parents:
        raise ValueError(f"{path} resolves to {target}, outside the root {repository}")
    # The working directory is already resolved, so it compares with `repository` directly.
    cwd: Path = Path.cwd()
    from_cwd: Path = path.resolve()
    if (
        not target.exists()
        and from_cwd != target
        and repository in from_cwd.parents
        and repository not in (cwd, *cwd.parents)
    ):
        raise ValueError(
            f"{path} is relative to --root {repository}: it names {target}, which does not "
            f"exist, not {from_cwd}; pass {from_cwd.relative_to(repository).as_posix()}"
        )
    return target


def run_validate(
    root: Path,
    config: ScanConfig,
    analyzer: Analyzer,
    *,
    write_graph: bool = False,
    baseline: Path | None = None,
    write_baseline: bool = False,
    accept_new: bool = False,
    against: str | None = None,
    against_config: ScanConfig | None = None,
    amendment: Path | None = None,
    write_amendment: bool = False,
    decided_by: str | None = None,
    rationale: str | None = None,
) -> tuple[RunResult, FilesToWrite]:
    """Validate contract structure, repository references and observed architecture.

    AD-46/AD-57: with `write_graph`, every rewritten graph page comes back for the caller to
    write, the way `run_init` returns its files.

    AD-52/AD-77: with `baseline`, the violations that file already states are known debt, and
    only the difference is reported - as `failures` with exit 1. A missing baseline may be
    created with `write_baseline`; an existing one is compared before it is rewritten. New or
    increased fingerprints refuse that rewrite unless `accept_new` is explicit, and the refused
    run's last failure names `--accept-new` (AD-106). Resolved-only drift may rewrite the file
    and shrinks the debt.

    AD-89: `declarations.measurement_budgets` selects deterministic scalar measurements whose
    accepted values share that baseline. A rise is new debt; a fall must rewrite the baseline.

    AD-61 (#11): with `against`, the contract at that Git revision - and, when `baseline` is
    also given, the baseline file there too - is compared with the one being validated;
    every widening (ir.widening.contract_widenings, ir.widening.baseline_widenings) is a
    `failures` entry with exit 1 unless `amendment` binds exactly this before/after pair.
    `write_amendment` writes that binding instead of checking it.

    AD-103: `baseline` and `amendment` are relative to `root`, like the contract, or absolute;
    either way one that resolves outside `root` is refused, so no write can land outside it.

    AD-105: a component package moved since `against` proposes a rename. One that keeps every
    relation between the old names, leaves no scanned module under an old prefix and renames the
    old contract into one that still parses is applied to the old side before comparing and
    named in `renames`.
    """
    if baseline is not None:
        try:
            baseline = _root_path(root, baseline)
        except ValueError as error:
            return _baseline_invalid(root / baseline, error, _BASELINE_INSIDE_ROOT), FilesToWrite()
    if amendment is not None:
        try:
            amendment = _root_path(root, amendment)
        except ValueError as error:
            return _amendment_invalid(root / amendment, error), FilesToWrite()
    known: tuple[KnownViolation, ...] = ()
    known_budgets: tuple[MeasurementBudget, ...] = ()
    baseline_exists = baseline is not None and baseline.exists()
    if baseline is not None and (not write_baseline or baseline_exists):
        try:
            parsed_baseline = parse_validation_baseline(decode_json(baseline.read_bytes()))
            known = parsed_baseline.violations
            known_budgets = parsed_baseline.budgets
        except (OSError, ValueError) as error:
            remedy = _BASELINE_CORRECT if baseline_exists else _BASELINE_WRITE
            return _baseline_invalid(baseline, error, remedy), FilesToWrite()
    parsed_contract = _parse_contract_or_invalid(root, config)
    if isinstance(parsed_contract, RunResult):
        return parsed_contract, FilesToWrite()
    contract = parsed_contract
    inside_tree = _inside_contract_tree(root, config.contract, contract)
    comparison_contract = contract if inside_tree is None else inside_tree.comparison_contract
    current_tree_digest = (
        contract_digest(contract) if inside_tree is None else inside_tree.comparison_digest
    )
    declarations = contract.declarations or ContractDeclarations()
    declared_budgets = tuple(item.name for item in declarations.measurement_budgets)
    if declared_budgets and baseline is None:
        return _budget_baseline_missing(), FilesToWrite()
    declared_labels = {*declared_budgets, *_name_budget_targets(declarations)}
    missing_budget_names = sorted(declared_labels - {item.label for item in known_budgets})
    if baseline is not None and baseline_exists and missing_budget_names and not write_baseline:
        missing = ", ".join(missing_budget_names)
        return _baseline_invalid(
            baseline,
            ValueError(f"measurement budget values are missing for: {missing}"),
            _BASELINE_WRITE,
        ), FilesToWrite()
    against_ctx, against_error = _resolve_against_context(
        root,
        config,
        against,
        baseline,
        amendment,
        write_amendment,
        decided_by,
        rationale,
        against_config,
    )
    if against_error is not None:
        return against_error, FilesToWrite()
    references = reference_diagnostics(root, config, contract)
    if references:
        return RunResult("validate", 2, diagnostics=references), FilesToWrite()
    observed = _observed_or_invalid(root, config, analyzer, contract)
    if isinstance(observed, RunResult):
        return observed, FilesToWrite()
    observation = observed
    violations = observed_violations(observation) if baseline is not None else ()
    resolved_public_entries = frozenset(
        _resolved_public_entries(contract, known, violations, observation)
    )
    diagnostics, edits = _repository_diagnostics(
        root,
        config,
        contract,
        observation,
        write_graph,
        baseline is None,
        resolved_public_entries,
        inside_tree,
    )
    try:
        observed_budgets = selected_budgets(measure_python_ratchets(observation), declared_budgets)
    except RatchetError as error:
        diagnostics.append(
            _diagnostic(
                "observation.incomplete",
                "",
                "measurement_budgets",
                f"The measurement budgets cannot be decided: {error}",
                "Repair the analyzer evidence and retry.",
            )
        )
        observed_budgets = ()
    budget_results = interface_budgets(declarations, observation)
    budget_diagnostics = interface_budget_diagnostics(
        budget_results, report_exceeded=baseline is None
    )
    observed_budgets = (
        *observed_budgets,
        *(_name_budget(item) for item in budget_results if not item.uncounted),
    )
    if baseline_exists:
        budget_results = _compared_budgets(budget_results, known_budgets)
    cycle_rules = _cycle_rule_ids(comparison_contract)
    baseline_new, baseline_resolved = (
        violation_drift_counts(known, violations, cycle_rules=cycle_rules)
        if baseline_exists
        else (0, 0)
    )
    budget_new = budget_regressions(known_budgets, observed_budgets) if baseline_exists else 0
    refused = (
        write_baseline and baseline_exists and bool(baseline_new or budget_new) and not accept_new
    )
    comparison = (
        compare_violations(known, violations, cycle_rules=cycle_rules, refused=refused)
        if baseline_exists
        else ()
    )
    budget_comparison = (
        compare_budgets(
            known_budgets, observed_budgets, against=against is not None, refused=refused
        )
        if baseline_exists
        else ()
    )
    baseline_failures = (*comparison, *budget_comparison) if not write_baseline or refused else ()
    interface_narrowings = tuple(
        f"resolved public entry: {entry} is no longer reached; remove it from {component}.public"
        for component, entry in sorted(resolved_public_entries)
    )
    rename = _rename_since(against_ctx, contract, observation, root, config, analyzer)
    widening_failures = _widening_failures(
        against_ctx,
        comparison_contract,
        rename,
        baseline,
        violations if write_baseline else known,
        observed_budgets if write_baseline else known_budgets,
        cycle_rules,
        current_tree_digest,
    )
    result = _observed_result(
        observation,
        [*diagnostics, *budget_diagnostics],
        (
            *baseline_failures,
            *interface_narrowings,
            *widening_failures,
            *((_WRITE_REFUSED,) if refused else ()),
        ),
        baseline_new=baseline_new if baseline is not None else None,
        baseline_resolved=baseline_resolved if baseline is not None else None,
        interface_budgets=budget_results or None,
    )
    if against is not None:
        result = replace(result, renames=rename.prefixes if rename is not None else ())
    # AD-100: a failing run whose calls_unresolved value moved from an accepted one names the
    # call sites against the other revision's code; only such a run pays for the second scan.
    # A revision without the contract has no declarations to observe that code under (AD-104).
    observed_calls = _calls_unresolved(observed_budgets)
    accepted_calls = {_calls_unresolved(known_budgets), _calls_unresolved(against_ctx.budgets)}
    if (
        against is not None
        and isinstance(against_ctx.contract, ArchitectureContract)
        and result.exit_code == 1
        and observed_calls is not None
        and accepted_calls != {observed_calls}
    ):
        changes, note = _unresolved_calls_since(root, config, analyzer, against, observation)
        result = replace(result, unresolved_call_changes=changes, unresolved_call_note=note)
    files, artifact = _artifact_files(
        write_baseline=write_baseline and not refused,
        baseline=baseline,
        violations=violations,
        budgets=observed_budgets,
        against=against_ctx,
        edits=edits,
        exit_code=result.exit_code,
        current_digest=current_tree_digest,
    )
    return (result if artifact is None else replace(result, artifact=artifact)), FilesToWrite(files)
