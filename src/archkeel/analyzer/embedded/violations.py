# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Evaluate declared class-A contract rules against scanner records."""

from __future__ import annotations

import sys
from collections import defaultdict
from collections.abc import Iterator, Sequence
from typing import Final, assert_never

from archkeel.ir.model import (
    AllowedDependencyRule,
    ArchitectureContract,
    ArchitectureRule,
    CompleteAssignmentRule,
    CompleteExternalScopeRule,
    CompleteRequiresRule,
    ContractComponent,
    EvidenceClass,
    ExternalDependencyScopeRule,
    ForbiddenConstructKind,
    ForbiddenConstructRule,
    ForbiddenDependencyRule,
    InterfaceBoundaryRule,
    NoComponentCyclesRule,
    SiblingIsolationRule,
    in_scope,
    package_owners,
    stable_id,
)

from .graph import strongly_connected_components
from .records import RawRecord, RecordData, classified


def _forbidden_dependency_matches(
    imports: Sequence[RawRecord],
    rules: Sequence[ArchitectureRule],
    components: tuple[tuple[str, tuple[str, ...]], ...],
) -> Iterator[tuple[ForbiddenDependencyRule, RawRecord]]:
    """Yield each (rule, import) pair a forbidden_dependency rule rejects.

    AD-18: interface_boundary reuses this to skip an import a forbidden rule already
    rejects, instead of a second matcher that could drift from this one (SPOT).
    """
    owners = package_owners(components)
    packages_by_label = dict(components)
    for rule in rules:
        if not isinstance(rule, ForbiddenDependencyRule):
            continue
        source_label = owners.get(rule.source)
        target_label = owners.get(rule.target)
        # A rule whose source and target each name a declared component package exactly,
        # with no target_symbol, decides (ir.decisions) and so enforces the whole ordered
        # component pair: every package of the source component against every package of
        # the target. A rule scoped to a submodule or a target_symbol keeps module matching.
        if rule.target_symbol is None and source_label is not None and target_label is not None:
            sources = packages_by_label[source_label]
            targets = packages_by_label[target_label]
        else:
            sources = (rule.source,)
            targets = (rule.target,)
        allowed_sources = frozenset(rule.allowed_sources)
        for item in imports:
            data = item["data"]
            if not any(in_scope(data["source_module"], package) for package in sources) or not any(
                in_scope(data["target_module"], package) for package in targets
            ):
                continue
            if data["source_module"] in allowed_sources:
                continue
            if rule.target_symbol is not None and data["symbol"] != rule.target_symbol:
                continue
            if data["under_type_checking"] and not rule.include_type_checking:
                continue
            yield rule, item


def _dependency_violations(
    matches: Iterator[tuple[ForbiddenDependencyRule, RawRecord]],
) -> list[RawRecord]:
    violations: list[RawRecord] = []
    for rule, item in matches:
        data = item["data"]
        target_name = ".".join(filter(None, (data["target_module"], data["symbol"])))
        violations.append(
            classified(
                item_id=stable_id("VIO", rule.id, item["id"]),
                evidence_class=EvidenceClass.VIOLATION,
                area="dependency_violations",
                kind="forbidden_dependency",
                title=f"{data['source_module']} imports forbidden {target_name}",
                subjects=[data["source_module"], target_name],
                evidence_ids=item["evidence_ids"],
                rule_ids=[rule.id],
                fact_ids=[item["id"]],
                data={
                    "source_module": data["source_module"],
                    "target_module": data["target_module"],
                    "symbol": data["symbol"],
                    "under_type_checking": data["under_type_checking"],
                },
            )
        )
    return sorted(violations, key=lambda item: item["id"])


_CONSTRUCT_SIGNALS: Final = {
    "cast_call": ForbiddenConstructKind.CAST,
    "getattr_call": ForbiddenConstructKind.GETATTR,
    "hasattr_call": ForbiddenConstructKind.HASATTR,
    "eval_call": ForbiddenConstructKind.EVAL,
    "exec_call": ForbiddenConstructKind.EXEC,
    "dynamic_import": ForbiddenConstructKind.DYNAMIC_IMPORT,
    "type_ignore": ForbiddenConstructKind.TYPE_IGNORE,
    "any_annotation": ForbiddenConstructKind.ANY_ANNOTATION,
    "placeholder_body": ForbiddenConstructKind.PLACEHOLDER_BODY,
    "assert_statement": ForbiddenConstructKind.ASSERT,
    "broad_except": ForbiddenConstructKind.BROAD_EXCEPT,
    "setattr_call": ForbiddenConstructKind.SETATTR,
    "delattr_call": ForbiddenConstructKind.DELATTR,
    "vars_call": ForbiddenConstructKind.VARS,
    "dunder_dict": ForbiddenConstructKind.DUNDER_DICT,
    "string_dispatch": ForbiddenConstructKind.STRING_DISPATCH,
}


def _construct_violations(
    signals: Sequence[RawRecord], rules: Sequence[ArchitectureRule]
) -> list[RawRecord]:
    violations: list[RawRecord] = []
    for rule in rules:
        if not isinstance(rule, ForbiddenConstructRule):
            continue
        for item in signals:
            construct = _CONSTRUCT_SIGNALS.get(item["kind"])
            owner = item["data"]["owner"]
            scope = owner.split(":", 1)[0]
            if (
                construct is None
                or construct not in rule.constructs
                or not in_scope(scope, rule.source)
                or any(in_scope(scope, allowed) for allowed in rule.allowed_sources)
                or scope in rule.exact_sources
            ):
                continue
            violations.append(
                classified(
                    item_id=stable_id("VIO", rule.id, item["id"]),
                    evidence_class=EvidenceClass.VIOLATION,
                    area="type_architecture",
                    kind=rule.kind,
                    title=f"{owner} uses forbidden {construct.value}",
                    subjects=[owner],
                    evidence_ids=item["evidence_ids"],
                    rule_ids=[rule.id],
                    fact_ids=[item["id"]],
                    data={"source": rule.source, "construct": construct.value},
                )
            )
    return sorted(violations, key=lambda item: item["id"])


def _external_dependency_violations(
    imports: Sequence[RawRecord], rules: Sequence[ArchitectureRule]
) -> list[RawRecord]:
    violations: list[RawRecord] = []
    for rule in rules:
        if not isinstance(rule, ExternalDependencyScopeRule):
            continue
        for item in imports:
            data = item["data"]
            source_module = data["source_module"]
            if (
                not in_scope(data["target_module"], rule.dependency)
                or any(in_scope(source_module, allowed) for allowed in rule.allowed_sources)
                or source_module in rule.exact_sources
            ):
                continue
            violations.append(
                classified(
                    item_id=stable_id("VIO", rule.id, item["id"]),
                    evidence_class=EvidenceClass.VIOLATION,
                    area="dependency_violations",
                    kind=rule.kind,
                    title=f"{source_module} imports {rule.dependency} outside its allowed scope",
                    subjects=[source_module, data["target_module"]],
                    evidence_ids=item["evidence_ids"],
                    rule_ids=[rule.id],
                    fact_ids=[item["id"]],
                    data={
                        "source_module": source_module,
                        "target_module": data["target_module"],
                        "dependency": rule.dependency,
                    },
                )
            )
    return sorted(violations, key=lambda item: item["id"])


_STANDARD_LIBRARY: Final = frozenset(sys.stdlib_module_names) | frozenset(sys.builtin_module_names)


def _external_completeness_violations(
    imports: Sequence[RawRecord], modules: Sequence[RawRecord], rules: Sequence[ArchitectureRule]
) -> list[RawRecord]:
    """AD-28: an import no rule names is undecided, not harmless."""
    declared = tuple(rule for rule in rules if isinstance(rule, ExternalDependencyScopeRule))
    internal_roots = {str(item["data"]["qualified_name"]).split(".")[0] for item in modules}
    violations: list[RawRecord] = []
    for rule in rules:
        if not isinstance(rule, CompleteExternalScopeRule):
            continue
        for item in imports:
            data = item["data"]
            target = data["target_module"]
            # A relative import resolves inside the scanned tree, so it is never external.
            if data["relative_level"] or not in_scope(data["source_module"], rule.source):
                continue
            root = target.split(".")[0]
            if root in internal_roots or root in _STANDARD_LIBRARY:
                continue
            if any(in_scope(target, declared.dependency) for declared in declared):
                continue
            violations.append(
                classified(
                    item_id=stable_id("VIO", rule.id, item["id"]),
                    evidence_class=EvidenceClass.VIOLATION,
                    area="dependency_violations",
                    kind=rule.kind,
                    title=f"{data['source_module']} imports undeclared {root}",
                    subjects=[data["source_module"], target],
                    evidence_ids=item["evidence_ids"],
                    rule_ids=[rule.id],
                    fact_ids=[item["id"]],
                    data={
                        "source": rule.source,
                        "source_module": data["source_module"],
                        "target_module": target,
                        "dependency": root,
                    },
                )
            )
    return sorted(violations, key=lambda item: item["id"])


def _assignment_violations(
    modules: Sequence[RawRecord], contract: ArchitectureContract, blank: frozenset[str]
) -> list[RawRecord]:
    violations: list[RawRecord] = []
    for rule in contract.rules:
        if not isinstance(rule, CompleteAssignmentRule):
            continue
        for item in modules:
            module = item["data"]["qualified_name"]
            # The namespace container and blank files hold no code a component could own.
            if (
                module == rule.source
                or module in blank
                or not in_scope(module, rule.source)
                or contract.component_for(module) is not None
            ):
                continue
            violations.append(
                classified(
                    item_id=stable_id("VIO", rule.id, item["id"]),
                    evidence_class=EvidenceClass.VIOLATION,
                    area="components",
                    kind=rule.kind,
                    title=f"{module} is not owned by exactly one component",
                    subjects=[module],
                    evidence_ids=item["evidence_ids"],
                    rule_ids=[rule.id],
                    fact_ids=[item["id"]],
                    data={"source": rule.source, "module": module},
                )
            )
    return sorted(violations, key=lambda item: item["id"])


def _component_cycle_violations(
    imports: Sequence[RawRecord], contract: ArchitectureContract
) -> list[RawRecord]:
    rules = [rule for rule in contract.rules if isinstance(rule, NoComponentCyclesRule)]
    if not rules:
        return []
    edge_imports: dict[tuple[str, str], list[RawRecord]] = defaultdict(list)
    for item in imports:
        source = contract.component_for(item["data"]["source_module"])
        target = contract.component_for(item["data"]["target_module"])
        if source is not None and target is not None and source != target:
            edge_imports[(source.label, target.label)].append(item)
    labels = [component.label for component in contract.components]
    violations: list[RawRecord] = []
    for members in strongly_connected_components(labels, edge_imports):
        if len(members) < 2:
            continue
        cycle_imports = [
            item
            for (source, target), items in edge_imports.items()
            if source in members and target in members
            for item in items
        ]
        violations.extend(
            classified(
                item_id=stable_id("VIO", rule.id, *members),
                evidence_class=EvidenceClass.VIOLATION,
                area="cycles",
                kind=rule.kind,
                title=f"Component cycle: {' ↔ '.join(members)}",
                subjects=members,
                evidence_ids=[
                    evidence_id for item in cycle_imports for evidence_id in item["evidence_ids"]
                ],
                rule_ids=[rule.id],
                fact_ids=[item["id"] for item in cycle_imports],
                data={"members": members},
            )
            for rule in rules
        )
    return sorted(violations, key=lambda item: item["id"])


def _interface_allows(
    data: RecordData, target: ContractComponent, exports_by_module: dict[str, frozenset[str]]
) -> bool:
    """Decide whether one cross-component import reaches the target's declared interface."""
    public = target.public
    if public is None:
        return True
    symbol = data["symbol"]
    if symbol is None:
        return data["target_module"] in public
    if symbol.startswith("_"):
        return False
    for entry in data["reexport_chain"]:
        module, _, name = entry.rpartition(".")
        if f"{module}:{name}" in public:
            return True
        exports = exports_by_module.get(module)
        if module in public and (not exports or name in exports):
            return True
    return False


def _interface_violations(
    imports: Sequence[RawRecord],
    contract: ArchitectureContract,
    modules: Sequence[RawRecord],
    forbidden_rejected_ids: frozenset[str],
) -> list[RawRecord]:
    rules = [rule for rule in contract.rules if isinstance(rule, InterfaceBoundaryRule)]
    if not rules:
        return []
    exports_by_module = {
        item["data"]["qualified_name"]: frozenset(item["data"]["all_exports"]) for item in modules
    }
    violations: list[RawRecord] = []
    for rule in rules:
        for item in imports:
            data = item["data"]
            source = contract.component_for(data["source_module"])
            target = contract.component_for(data["target_module"])
            if (
                source is None
                or target is None
                or source == target
                or target.public is None
                or (data["under_type_checking"] and not rule.include_type_checking)
                # AD-18: a forbidden edge has no legitimate interface to reach, so it is
                # reported once, as the forbidden_dependency violation.
                or item["id"] in forbidden_rejected_ids
                or _interface_allows(data, target, exports_by_module)
            ):
                continue
            target_name = ".".join(filter(None, (data["target_module"], data["symbol"])))
            violations.append(
                classified(
                    item_id=stable_id("VIO", rule.id, item["id"]),
                    evidence_class=EvidenceClass.VIOLATION,
                    area="api_surface",
                    kind="interface_boundary",
                    title=f"{data['source_module']} reaches {target_name} "
                    "outside its declared interface",
                    subjects=[data["source_module"], target_name],
                    evidence_ids=item["evidence_ids"],
                    rule_ids=[rule.id],
                    fact_ids=[item["id"]],
                    data={
                        "source_module": data["source_module"],
                        "target_module": data["target_module"],
                        "symbol": data["symbol"],
                        "source_component": source.label,
                        "target_component": target.label,
                    },
                )
            )
    return sorted(violations, key=lambda item: item["id"])


def rule_scopes(rule: ArchitectureRule) -> dict[str, tuple[str, ...]]:
    """Name the module selectors whose absence would make a rule vacuous."""
    if isinstance(rule, ForbiddenDependencyRule | AllowedDependencyRule):
        return {"source": (rule.source,), "target": (rule.target,)}
    if isinstance(rule, ExternalDependencyScopeRule):
        scopes = {"allowed_sources": rule.allowed_sources, "exact_sources": rule.exact_sources}
        return {side: values for side, values in scopes.items() if values}
    # complete_requires selects no module: it speaks about every cross-component import, so a
    # scope here would have rule_subject_failures match it against scanned module names and
    # call the rule vacuous.
    if isinstance(rule, NoComponentCyclesRule | InterfaceBoundaryRule | CompleteRequiresRule):
        return {}
    if isinstance(rule, SiblingIsolationRule):
        return {"members": rule.members}
    if isinstance(
        rule, ForbiddenConstructRule | CompleteAssignmentRule | CompleteExternalScopeRule
    ):
        return {"source": (rule.source,)}
    assert_never(rule)


def rule_subject_failures(
    rules: Sequence[ArchitectureRule], module_names: set[str]
) -> list[RawRecord]:
    """Flag each rule whose scope selectors match no scanned module."""
    rule_failures: list[RawRecord] = []
    for rule in rules:
        scopes = rule_scopes(rule)
        matches = {
            side: sum(
                any(in_scope(module, scope) for scope in side_scopes) for module in module_names
            )
            for side, side_scopes in scopes.items()
        }
        missing = [side for side, count in matches.items() if count == 0]
        if missing:
            rule_failures.append(
                classified(
                    item_id=stable_id("UNKNOWN-RULE-SUBJECTS", rule.id),
                    evidence_class=EvidenceClass.UNKNOWN,
                    area="analysis_coverage",
                    kind="rule-without-subjects",
                    title=f"{rule.id}: no scanned modules for {', '.join(missing)}",
                    subjects=[scope for side in missing for scope in scopes[side]],
                    rule_ids=[rule.id],
                    data={
                        "missing": missing,
                        **{f"{side}_matches": count for side, count in matches.items()},
                    },
                )
            )
    return rule_failures


def _sibling_violations(
    imports: Sequence[RawRecord], rules: Sequence[ArchitectureRule]
) -> list[RawRecord]:
    """AD-25: peers of one declared set reach shared modules, never each other."""
    violations: list[RawRecord] = []
    for rule in rules:
        if not isinstance(rule, SiblingIsolationRule):
            continue
        for item in imports:
            data = item["data"]
            source = next(
                (member for member in rule.members if in_scope(data["source_module"], member)), None
            )
            target = next(
                (member for member in rule.members if in_scope(data["target_module"], member)), None
            )
            if source is None or target is None or source == target:
                continue
            if data["under_type_checking"] and not rule.include_type_checking:
                continue
            violations.append(
                classified(
                    item_id=stable_id("VIO", rule.id, item["id"]),
                    evidence_class=EvidenceClass.VIOLATION,
                    area="dependency_violations",
                    kind="sibling_isolation",
                    title=f"{data['source_module']} imports its peer {data['target_module']}",
                    subjects=[data["source_module"], data["target_module"]],
                    evidence_ids=item["evidence_ids"],
                    rule_ids=[rule.id],
                    fact_ids=[item["id"]],
                    data={
                        "source_module": data["source_module"],
                        "target_module": data["target_module"],
                        "source": source,
                    },
                )
            )
    return sorted(violations, key=lambda item: item["id"])


def _requires_covers(source: ContractComponent, target_label: str, target_module: str) -> bool:
    """True when a `requires` entry names the target and, if it lists `through`, one of those
    prefixes names the imported module (AD-42)."""
    return any(
        entry.component == target_label
        and (not entry.through or any(in_scope(target_module, m) for m in entry.through))
        for entry in source.requires or ()
    )


def requires_violations(
    imports: Sequence[RawRecord], contract: ArchitectureContract
) -> list[RawRecord]:
    """AD-32: a cross-component import no `requires` entry of the source covers is a violation.

    Public because a declared inside is evaluated by the same function against its own
    contract (AD-34). It reads finished import records, so the second level costs no second
    scan, and an import whose modules the inner contract does not own is skipped by
    `component_for` the way any out-of-scope import is.
    """
    rules = [rule for rule in contract.rules if isinstance(rule, CompleteRequiresRule)]
    if not rules:
        return []
    violations: list[RawRecord] = []
    for rule in rules:
        for item in imports:
            data = item["data"]
            source = contract.component_for(data["source_module"])
            target = contract.component_for(data["target_module"])
            if (
                source is None
                or target is None
                or source == target
                or (data["under_type_checking"] and not rule.include_type_checking)
                or _requires_covers(source, target.label, data["target_module"])
            ):
                continue
            violations.append(
                classified(
                    item_id=stable_id("VIO", rule.id, item["id"]),
                    evidence_class=EvidenceClass.VIOLATION,
                    area="dependency_violations",
                    kind=rule.kind,
                    title=f"{source.label} imports {target.label} without requiring it",
                    subjects=[data["source_module"], data["target_module"]],
                    evidence_ids=item["evidence_ids"],
                    rule_ids=[rule.id],
                    fact_ids=[item["id"]],
                    data={
                        "source_module": data["source_module"],
                        "target_module": data["target_module"],
                        "source_component": source.label,
                        "target_component": target.label,
                    },
                )
            )
    return sorted(violations, key=lambda item: item["id"])


def rule_violations(
    *,
    imports: Sequence[RawRecord],
    typing_signals: Sequence[RawRecord],
    constructs: Sequence[RawRecord],
    modules: Sequence[RawRecord],
    blank_modules: frozenset[str],
    contract: ArchitectureContract,
) -> list[RawRecord]:
    """Evaluate every declared contract rule and return the sorted violation records."""
    components = tuple((component.label, component.packages) for component in contract.components)
    forbidden_matches = list(_forbidden_dependency_matches(imports, contract.rules, components))
    forbidden_rejected_ids = frozenset(item["id"] for _, item in forbidden_matches)
    return sorted(
        [
            *_dependency_violations(iter(forbidden_matches)),
            *_construct_violations([*typing_signals, *constructs], contract.rules),
            *_external_dependency_violations(imports, contract.rules),
            *_external_completeness_violations(imports, modules, contract.rules),
            *requires_violations(imports, contract),
            *_assignment_violations(modules, contract, blank_modules),
            *_component_cycle_violations(imports, contract),
            *_interface_violations(imports, contract, modules, forbidden_rejected_ids),
            *_sibling_violations(imports, contract.rules),
        ],
        key=lambda item: item["id"],
    )
