# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Validate architecture-contract quality against typed observations."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import replace
from pathlib import Path, PurePosixPath
from typing import TypeVar

from archkeel.ir.codec import (
    CONTRACT_SCHEMA_VERSION,
    ContractVersionError,
    contract_provenance_paths,
    decode_json,
    parse_contract,
)
from archkeel.ir.decisions import agent_decisions, open_decisions
from archkeel.ir.model import (
    AllowedDependencyRule,
    ArchitectureContract,
    CompleteAssignmentRule,
    ContractDeclarations,
    Diagnostic,
    DiagnosticCode,
    ExternalDependencyScopeRule,
    ForbiddenConstructRule,
    ForbiddenDependencyRule,
    InterfaceBoundaryRule,
    Observation,
    RecordData,
    RunResult,
    in_scope,
)

from .ports import Analyzer, ScanConfig
from .report import observe_repository
from .run import inspect_observation

COMPONENT_GRAPH_MARKER = "<!-- archkeel-component-graph -->"
_REPEATED_RATIONALE = re.compile(r"(?:The )?\S+ does not depend on \S+\.", re.IGNORECASE)
_PLACEHOLDER_RATIONALE = re.compile(r"(?:todo|tbd|placeholder)(?:\b|:)", re.IGNORECASE)
_GRAPH_EDGE = re.compile(r"\s*([a-z][a-z0-9_]*)\s*-->\s*([a-z][a-z0-9_]*)\s*")


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
            f"The component pair is {'observed' if decision.observed else 'not observed'} at "
            f"{decision.import_sites} import site(s) and is undecided: no allowed_dependency or "
            "forbidden_dependency rule covers it.",
            "Decide the pair with an allowed_dependency or forbidden_dependency rule "
            "and rationale.",
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


def _entry_used(entry: str, records: list[RecordData]) -> bool:
    """Match one public entry's usage the way `_interface_allows` walks reexport_chain.

    Deliberately looser than the analyzer's runtime check: no `__all__` gate and no
    underscore rejection, since a public entry naming a private or unexported name is
    a rule violation already reported elsewhere, not an unused-entry drift signal.
    """
    module, colon, name = entry.partition(":")
    for data in records:
        chain = data.get("reexport_chain")
        chain_items = chain if isinstance(chain, tuple) else ()
        if colon:
            if any(item == f"{module}.{name}" for item in chain_items if isinstance(item, str)):
                return True
            continue
        if data.get("target_module") == module:
            return True
        for item in chain_items:
            if isinstance(item, str) and item.rpartition(".")[0] == module:
                return True
    return False


def interface_diagnostics(
    contract: ArchitectureContract, observation: Observation
) -> tuple[Diagnostic, ...]:
    """Require a declared interface for inbound imports and usage for declared entries."""
    if not any(isinstance(rule, InterfaceBoundaryRule) for rule in contract.rules):
        return ()
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
            continue
        for item, entry in enumerate(component.public):
            if not _entry_used(entry, records):
                diagnostics.append(
                    _diagnostic(
                        "interface.unused",
                        f"/components/{index}/public/{item}",
                        entry,
                        "No cross-component import reaches this public entry.",
                        "Remove the entry or confirm another component should use it.",
                    )
                )
    return tuple(diagnostics)


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
    return tuple(diagnostics)


def graph_diagnostics(
    contract: ArchitectureContract,
    observation: Observation,
    documents: tuple[tuple[str, str], ...],
) -> tuple[Diagnostic, ...]:
    """Require exactly one marked Mermaid graph matching observed component edges."""
    graphs: list[tuple[str, frozenset[tuple[str, str]]]] = []
    for path, content in documents:
        for fragment in content.split(COMPONENT_GRAPH_MARKER)[1:]:
            if "```mermaid\n" not in fragment:
                continue
            mermaid = fragment.split("```mermaid\n", 1)[1].split("```", 1)[0]
            graphs.append(
                (
                    path,
                    frozenset(
                        (match.group(1), match.group(2))
                        for line in mermaid.splitlines()
                        if (match := _GRAPH_EDGE.fullmatch(line))
                    ),
                )
            )
    if len(graphs) != 1:
        return (
            _diagnostic(
                "graph.count",
                "/components",
                "architecture component graph",
                f"Expected one marked Mermaid component graph, found {len(graphs)}.",
                "Keep one graph after the archkeel-component-graph marker in contract provenance.",
            ),
        )
    path, declared = graphs[0]
    observed = observed_component_edges(contract, observation)
    if declared == observed:
        return ()
    missing = ", ".join(f"{a}->{b}" for a, b in sorted(observed - declared)) or "none"
    extra = ", ".join(f"{a}->{b}" for a, b in sorted(declared - observed)) or "none"
    return (
        _diagnostic(
            "graph.drift",
            "/components",
            path,
            "The marked component graph differs from observed imports; "
            f"missing: {missing}; extra: {extra}.",
            "Regenerate the marked Mermaid graph from the observed component edges.",
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
        ("/declarations/public_api_provenance", declarations.public_api_provenance),
        ("/declarations/context_roots_provenance", declarations.context_roots_provenance),
    )


def _namespace_references(contract: ArchitectureContract) -> list[tuple[str, str]]:
    """Collect every contract-declared name that must resolve inside the scan namespace."""
    declarations = contract.declarations or ContractDeclarations()
    names: list[tuple[str, str]] = []
    for index, component in enumerate(contract.components):
        names.extend(
            (f"/components/{index}/packages/{item}", value)
            for item, value in enumerate(component.packages)
        )
        if component.public is not None:
            names.extend(
                (f"/components/{index}/public/{item}", value.split(":", 1)[0])
                for item, value in enumerate(component.public)
            )
    for index, rule in enumerate(contract.rules):
        if isinstance(
            rule,
            ForbiddenDependencyRule
            | AllowedDependencyRule
            | ForbiddenConstructRule
            | CompleteAssignmentRule,
        ):
            names.append((f"/rules/{index}/source", rule.source))
        if isinstance(rule, ForbiddenDependencyRule | AllowedDependencyRule):
            names.append((f"/rules/{index}/target", rule.target))
        if isinstance(rule, ForbiddenDependencyRule | ExternalDependencyScopeRule):
            names.extend(
                (f"/rules/{index}/allowed_sources/{item}", value)
                for item, value in enumerate(rule.allowed_sources)
            )
    names.extend(
        (f"/declarations/public_api/{index}", value)
        for index, value in enumerate(declarations.public_api)
    )
    names.extend(
        (f"/declarations/context_roots/{index}", value)
        for index, value in enumerate(declarations.context_roots)
    )
    for index, scope in enumerate(declarations.review_scopes):
        names.extend(
            (f"/declarations/review_scopes/{index}/subjects/{item}", value)
            for item, value in enumerate(scope.subjects)
        )
    names.extend(
        (f"/declarations/spot_owners/{index}/owner", owner.owner)
        for index, owner in enumerate(declarations.spot_owners)
    )
    return names


def _public_diagnostics(contract: ArchitectureContract) -> list[Diagnostic]:
    """Require each public entry to be owned by its component and never underscore-named."""
    diagnostics = []
    for index, component in enumerate(contract.components):
        if component.public is None:
            continue
        for item, entry in enumerate(component.public):
            module, _, name = entry.partition(":")
            pointer = f"/components/{index}/public/{item}"
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


def reference_diagnostics(
    root: Path,
    config: ScanConfig,
    contract: ArchitectureContract,
    observation: Observation | None = None,
) -> tuple[Diagnostic, ...]:
    """Validate repository-dependent namespace, package and provenance references."""
    names = _namespace_references(contract)
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
            relative = PurePosixPath(value)
            target = (repository / value).resolve()
            safe = not relative.is_absolute() and ".." not in relative.parts and "\\" not in value
            if not safe or not target.is_relative_to(repository) or not target.is_file():
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
        modules = {
            module_name
            for record in observation.records("modules") or ()
            if isinstance((module_name := record.data.get("qualified_name")), str)
        }
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


def observation_diagnostics(
    contract: ArchitectureContract,
    observation: Observation,
    documents: tuple[tuple[str, str], ...],
) -> tuple[Diagnostic, ...]:
    """Validate rules, closed-world coverage and architecture documentation."""
    rule_index = {rule.id: index for index, rule in enumerate(contract.rules)}
    diagnostics = [
        *closed_world_diagnostics(contract, observation),
        *interface_diagnostics(contract, observation),
        *rationale_diagnostics(contract),
        *graph_diagnostics(contract, observation, documents),
    ]
    for record in observation.records("violations") or ():
        rule_id = record.rule_ids[0] if record.rule_ids else record.id
        diagnostics.append(
            _diagnostic(
                "rule.violated",
                f"/rules/{rule_index.get(rule_id, 0)}",
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


def run_validate(root: Path, config: ScanConfig, analyzer: Analyzer) -> RunResult:
    """Validate contract structure, repository references and observed architecture."""
    contract_path = root / config.contract
    try:
        contract = parse_contract(decode_json(contract_path.read_bytes()))
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
    references = reference_diagnostics(root, config, contract)
    if references:
        return RunResult("validate", 2, diagnostics=references)
    observed = observe_repository(root, config, analyzer)
    observation = observed.observation
    if observed.diagnostics or observation is None:
        return RunResult(
            "validate",
            2,
            diagnostics=tuple(
                replace(item, pointer=item.pointer or "") for item in observed.diagnostics
            ),
            coverage=observed.coverage,
        )
    diagnostics = [*reference_diagnostics(root, config, contract, observation)]
    documents = tuple(
        (path, (root / path).read_text()) for path in contract_provenance_paths(contract)
    )
    diagnostics.extend(observation_diagnostics(contract, observation, documents))
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
    counts = agent_decisions(contract)
    if diagnostics:
        return RunResult(
            "validate",
            2,
            diagnostics=_sorted(diagnostics),
            coverage=observation.coverage,
            python_version=observation.python_version,
            open_decisions=decisions,
            agent_decisions=counts,
        )
    return RunResult(
        "validate",
        0,
        observation_complete="PASS",
        declared_rules=declared,
        expectation_fulfilled="n/a",
        coverage=observation.coverage,
        python_version=observation.python_version,
        measurements=measurements,
        open_decisions=decisions,
        agent_decisions=counts,
    )
