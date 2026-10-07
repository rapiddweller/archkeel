# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Observation validation diagnostics."""

from __future__ import annotations

from archkeel.ir.model import (
    ArchitectureContract,
    Diagnostic,
    InsideContractTree,
    Observation,
    ReportLocation,
    text_value,
)

from ..report import VIOLATION_REMEDY
from .closed_world import closed_world_diagnostics
from .diagnostics import _diagnostic, _sorted
from .graphs import graph_diagnostics
from .public_api import compatibility_diagnostics, interface_diagnostics, public_api_diagnostics
from .rationale import rationale_diagnostics


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


def _responsibility_diagnostics(
    contract: ArchitectureContract,
    inside_tree: InsideContractTree | None,
    contract_path: str | None,
) -> list[Diagnostic]:
    """Flag architect-decided components whose responsibility list is empty."""
    contracts: list[tuple[ArchitectureContract, str | None]] = [(contract, None)]
    if inside_tree is not None:
        contracts.extend((mount.contract, mount.path) for mount in inside_tree.mounts)
    diagnostics = []
    for reviewed_contract, path in contracts:
        for index, component in enumerate(reviewed_contract.components):
            if component.decided_by != "architect" or any(
                value.strip() for value in component.responsibilities
            ):
                continue
            location = f" in {path}" if path is not None else ""
            diagnostics.append(
                _diagnostic(
                    "responsibility.missing",
                    f"/components/{index}/responsibilities",
                    f"{component.label}{location}",
                    "The architect-decided component has no responsibility declaration.",
                    "Ask the architect to declare the component's intended responsibilities.",
                    contract_path=path or contract_path,
                )
            )
    return diagnostics


def observation_diagnostics(
    contract: ArchitectureContract,
    observation: Observation,
    documents: tuple[tuple[str, str], ...],
    *,
    report_violations: bool = True,
    resolved_public_entries: frozenset[tuple[str, str]] = frozenset(),
    inside_tree: InsideContractTree | None = None,
    contract_path: str | None = None,
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
    evidence = {item.id: item for item in observation.evidence}
    for record in reported:
        rule_id = record.rule_ids[0] if record.rule_ids else record.id
        index = rule_index.get(rule_id)
        locations = tuple(
            sorted(
                {
                    ReportLocation(item.file, item.line)
                    for evidence_id in record.evidence_ids
                    if (item := evidence.get(evidence_id)) is not None
                },
                key=lambda item: (item.path, item.line),
            )
        )
        diagnostics.append(
            _diagnostic(
                "rule.violated",
                f"/rules/{index}" if index is not None else inside_pointers.get(rule_id, ""),
                rule_id,
                (
                    f"The declared requires permission violates the layer order: {record.title}"
                    if record.kind == "layer_order"
                    else f"The observed code violates the declared rule: {record.title}"
                ),
                (
                    "Change the permission or layer, or amend the order with owner approval."
                    if record.kind == "layer_order"
                    else VIOLATION_REMEDY
                ),
                locations,
            )
        )
    diagnostics.extend(_responsibility_diagnostics(contract, inside_tree, contract_path))
    return _sorted(diagnostics)
