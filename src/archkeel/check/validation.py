# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Validate architecture-contract quality against typed observations."""

from __future__ import annotations

import re
from collections import Counter

from archkeel.ir.model import ArchitectureContract, Diagnostic, Observation

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
