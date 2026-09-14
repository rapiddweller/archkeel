# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Validate architecture-contract quality against typed observations."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import replace
from pathlib import Path, PurePosixPath

from archkeel.ir.codec import (
    CONTRACT_SCHEMA_VERSION,
    ContractVersionError,
    contract_provenance_paths,
    decode_json,
    parse_contract,
)
from archkeel.ir.model import (
    ArchitectureContract,
    ContractDeclarations,
    Diagnostic,
    Observation,
    RunResult,
)

from .ports import Analyzer, ScanConfig
from .report import observe_repository
from .run import inspect_observation

COMPONENT_GRAPH_MARKER = "<!-- archkeel-component-graph -->"
_REPEATED_RATIONALE = re.compile(r"(?:The )?\S+ does not depend on \S+\.", re.IGNORECASE)
_PLACEHOLDER_RATIONALE = re.compile(r"(?:todo|tbd|placeholder)(?:\b|:)", re.IGNORECASE)
_GRAPH_EDGE = re.compile(r"\s*([a-z][a-z0-9_]*)\s*-->\s*([a-z][a-z0-9_]*)\s*")


def _diagnostic(pointer: str, subject: str, claim: str, remedy: str) -> Diagnostic:
    return Diagnostic("contract_invalid", subject, claim, remedy, pointer)


def _package_owners(contract: ArchitectureContract) -> dict[str, str]:
    return {
        package: component.label
        for component in contract.components
        for package in component.packages
    }


def _component_for(module: str, owners: dict[str, str]) -> str | None:
    matches = [
        label
        for package, label in owners.items()
        if module == package or module.startswith(package + ".")
    ]
    return matches[0] if len(matches) == 1 else None


def observed_component_edges(
    contract: ArchitectureContract, observation: Observation
) -> frozenset[tuple[str, str]]:
    """Project module imports onto declared component labels."""
    owners = _package_owners(contract)
    edges: set[tuple[str, str]] = set()
    for record in observation.records("imports") or ():
        source_module = record.data.get("source_module")
        target_module = record.data.get("target_module")
        if not isinstance(source_module, str) or not isinstance(target_module, str):
            continue
        source = _component_for(source_module, owners)
        target = _component_for(target_module, owners)
        if source is not None and target is not None and source != target:
            edges.add((source, target))
    return frozenset(edges)


def closed_world_diagnostics(
    contract: ArchitectureContract, observation: Observation
) -> tuple[Diagnostic, ...]:
    """Require each ordered component pair to be observed or explicitly forbidden."""
    owners = _package_owners(contract)
    labels = {component.label for component in contract.components}
    expected = {(source, target) for source in labels for target in labels if source != target}
    observed = set(observed_component_edges(contract, observation))
    forbidden_items = [
        (owners[rule.source], owners[rule.target])
        for rule in contract.rules
        if rule.source in owners and rule.target in owners
    ]
    forbidden = set(forbidden_items)
    diagnostics = [
        _diagnostic(
            "/rules",
            f"{source} -> {target}",
            "The component pair has neither an observed import nor a forbidden_dependency rule.",
            "Add the observed dependency or forbid the component pair with a rationale.",
        )
        for source, target in sorted(expected - observed - forbidden)
    ]
    diagnostics.extend(
        _diagnostic(
            "/rules",
            f"{source} -> {target}",
            "An observed component dependency is also forbidden.",
            "Remove the dependency or correct the forbidden_dependency rule.",
        )
        for source, target in sorted(observed & forbidden)
    )
    diagnostics.extend(
        _diagnostic(
            "/rules",
            f"{source} -> {target}",
            "The component pair has duplicate forbidden_dependency rules.",
            "Keep one forbidden_dependency rule for this ordered component pair.",
        )
        for (source, target), count in sorted(Counter(forbidden_items).items())
        if count > 1
    )
    return tuple(diagnostics)


def rationale_diagnostics(contract: ArchitectureContract) -> tuple[Diagnostic, ...]:
    """Reject placeholder rationales and rationales that only repeat the rule."""
    diagnostics = []
    for index, rule in enumerate(contract.rules):
        rationale = rule.rationale.strip()
        if _REPEATED_RATIONALE.fullmatch(rationale):
            claim = "The rationale repeats the forbidden dependency without explaining why."
        elif _PLACEHOLDER_RATIONALE.match(rationale):
            claim = "The rationale is a placeholder."
        else:
            continue
        diagnostics.append(
            _diagnostic(
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


def _inside_namespace(value: str, namespace: str) -> bool:
    return value == namespace or value.startswith(namespace + ".")


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


def reference_diagnostics(
    root: Path,
    config: ScanConfig,
    contract: ArchitectureContract,
    observation: Observation | None = None,
) -> tuple[Diagnostic, ...]:
    """Validate repository-dependent namespace, package and provenance references."""
    declarations = contract.declarations or ContractDeclarations()
    names: list[tuple[str, str]] = []
    for index, component in enumerate(contract.components):
        names.extend(
            (f"/components/{index}/packages/{item}", value)
            for item, value in enumerate(component.packages)
        )
    for index, rule in enumerate(contract.rules):
        names.extend(
            ((f"/rules/{index}/source", rule.source), (f"/rules/{index}/target", rule.target))
        )
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
    diagnostics = [
        _diagnostic(
            pointer,
            value,
            f"The reference is outside namespace {config.namespace}.",
            "Use a qualified name inside the configured namespace.",
        )
        for pointer, value in names
        if not _inside_namespace(value, config.namespace)
    ]
    repository = root.resolve()
    for pointer, values in _provenance(contract):
        for index, value in enumerate(values):
            relative = PurePosixPath(value)
            target = (repository / value).resolve()
            safe = not relative.is_absolute() and ".." not in relative.parts and "\\" not in value
            if not safe or not target.is_relative_to(repository) or not target.is_file():
                diagnostics.append(
                    _diagnostic(
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
                if not any(
                    module == package or module.startswith(package + ".") for module in modules
                ):
                    diagnostics.append(
                        _diagnostic(
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
        *rationale_diagnostics(contract),
        *graph_diagnostics(contract, observation, documents),
    ]
    for record in observation.records("unknowns") or ():
        if record.kind == "rule-without-subjects":
            for rule_id in record.rule_ids:
                diagnostics.append(
                    _diagnostic(
                        f"/rules/{rule_index.get(rule_id, 0)}",
                        rule_id,
                        "The rule matched no scanned source or target module.",
                        "Correct the rule selector or scan scope.",
                    )
                )
    for record in observation.records("violations") or ():
        rule_id = record.rule_ids[0] if record.rule_ids else record.id
        diagnostics.append(
            _diagnostic(
                f"/rules/{rule_index.get(rule_id, 0)}",
                rule_id,
                f"The observed code violates the declared rule: {record.title}",
                "Remove the dependency or amend the contract with owner approval.",
            )
        )
    return _sorted(diagnostics)


def invalid_result(subject: str, error: Exception, pointer: str = "") -> RunResult:
    return RunResult(
        "validate",
        2,
        diagnostics=(
            _diagnostic(
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
    if observed.diagnostics:
        return RunResult(
            "validate",
            2,
            diagnostics=tuple(
                replace(item, pointer=item.pointer or "") for item in observed.diagnostics
            ),
            coverage=observed.coverage,
        )
    observation = observed.observation
    assert observation is not None
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
                "",
                "observation",
                f"The observation is incomplete: {error}",
                "Repair the analyzer evidence and retry.",
            )
        )
        measurements = None
        declared = "FAIL"
    if diagnostics:
        return RunResult(
            "validate",
            2,
            diagnostics=_sorted(diagnostics),
            coverage=observation.coverage,
            python_version=observation.python_version,
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
    )
