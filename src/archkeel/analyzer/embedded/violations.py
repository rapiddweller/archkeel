# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Evaluate declared class-A contract rules against scanner records."""

from __future__ import annotations

import sys
from collections import defaultdict
from collections.abc import Iterator, Sequence
from collections.abc import Set as AbstractSet
from typing import Final, assert_never

from archkeel.ir.model import (
    AllowedDependencyRule,
    ArchitectureContract,
    ArchitectureRule,
    BoundaryTypesRule,
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
    SymbolPlacementRule,
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
    "string_literal_compare": ForbiddenConstructKind.STRING_LITERAL_COMPARE,
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


def exports_by_module(modules: Sequence[RawRecord]) -> dict[str, frozenset[str]]:
    """Map each scanned module to its literal `__all__`, or an empty set when it declares none.

    Shared by `interface_boundary` and `boundary_types` (AD-63): both need the same answer to
    "does this module's `__all__` narrow which of its names are public", so both read it from
    here instead of two readings of the same `modules` section drifting apart. Public, not a
    module-private helper: `scanner.scan_repository` computes it once and hands it to both
    `rule_violations` and `rule_subject_failures` too (issue #56).
    """
    return {
        item["data"]["qualified_name"]: frozenset(item["data"]["all_exports"]) for item in modules
    }


def _facade_covers(
    module: str,
    name: str,
    component: ContractComponent,
    exports_by_module: dict[str, frozenset[str]],
) -> bool:
    """True when `component.public` declares `module:name`, directly or through `module`'s
    `__all__` (AD-9): the one answer both `interface_boundary` (does a cross-component import
    reach its target) and `boundary_types` (does an annotation name a type its own component
    already declares) need, given the module and name already stopped at rather than a chain to
    walk -- a chain, when one exists, is the caller's own job.
    """
    public = component.public
    if public is None or name.startswith("_"):
        return False
    if f"{module}:{name}" in public:
        return True
    exports = exports_by_module.get(module)
    return module in public and (not exports or name in exports)


def _interface_allows(
    data: RecordData, target: ContractComponent, exports_by_module: dict[str, frozenset[str]]
) -> bool:
    """Decide whether one cross-component import reaches the target's declared interface."""
    if target.public is None:
        return True
    symbol = data["symbol"]
    if symbol is None:
        return data["target_module"] in target.public
    if symbol.startswith("_"):
        return False
    for entry in data["reexport_chain"]:
        module, _, name = entry.rpartition(".")
        if _facade_covers(module, name, target, exports_by_module):
            return True
    return False


def _interface_violations(
    imports: Sequence[RawRecord],
    contract: ArchitectureContract,
    exports_by_module: dict[str, frozenset[str]],
    forbidden_rejected_ids: frozenset[str],
) -> list[RawRecord]:
    rules = [rule for rule in contract.rules if isinstance(rule, InterfaceBoundaryRule)]
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
        rule,
        ForbiddenConstructRule
        | CompleteAssignmentRule
        | CompleteExternalScopeRule
        | BoundaryTypesRule,
    ):
        return {"source": (rule.source,)}
    if isinstance(rule, SymbolPlacementRule):
        scopes = {"source": (rule.source,)}
        scopes.update(
            {
                side: values
                for side, values in (
                    ("allowed_sources", rule.allowed_sources),
                    ("exact_sources", rule.exact_sources),
                )
                if values
            }
        )
        return scopes
    assert_never(rule)


def _boundary_type_subject_modules(
    rule: BoundaryTypesRule,
    symbols: Sequence[RawRecord],
    contract: ArchitectureContract,
    exports_by_module: dict[str, frozenset[str]],
) -> frozenset[str]:
    """Modules carrying at least one function `rule` actually inspects (issue #56).

    `source` matching a scanned module used to be enough: every non-underscore, module-level
    function under it was a subject. AD-63 reads the declared facade instead, so a component
    whose `public` is `None`, or whose `public` never covers a function under `source`, gives
    the rule zero functions to check -- a scanned module is no longer the same thing as a
    decided subject for this one rule kind, and `rule_subject_failures` has to see that instead
    of reading an empty result as a clean pass.
    """
    return frozenset(
        module
        for item in symbols
        if (found := _facade_positions(item, rule, contract, exports_by_module)) is not None
        for module in (found[0],)
    )


def rule_subject_failures(
    rules: Sequence[ArchitectureRule],
    module_names: set[str],
    *,
    symbols: Sequence[RawRecord] = (),
    contract: ArchitectureContract | None = None,
    exports_by_module: dict[str, frozenset[str]] | None = None,
) -> list[RawRecord]:
    """Flag each rule whose scope selectors match no scanned module -- or, for `boundary_types`,
    no function its own component's declared facade actually covers (AD-63, issue #56): a rule
    that can only pass by finding nothing to check must report UNKNOWN, not PASS.
    """
    rule_failures: list[RawRecord] = []
    for rule in rules:
        scopes = rule_scopes(rule)
        subjects: AbstractSet[str] = module_names
        facade_scoped = False
        if isinstance(rule, BoundaryTypesRule) and contract is not None:
            subjects = _boundary_type_subject_modules(
                rule, symbols, contract, exports_by_module or {}
            )
            facade_scoped = True
        matches = {
            side: sum(any(in_scope(module, scope) for scope in side_scopes) for module in subjects)
            for side, side_scopes in scopes.items()
        }
        missing = [side for side, count in matches.items() if count == 0]
        if missing:
            reason = "no declared facade function" if facade_scoped else "no scanned modules"
            rule_failures.append(
                classified(
                    item_id=stable_id("UNKNOWN-RULE-SUBJECTS", rule.id),
                    evidence_class=EvidenceClass.UNKNOWN,
                    area="analysis_coverage",
                    kind="rule-without-subjects",
                    title=f"{rule.id}: {reason} for {', '.join(missing)}",
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


def _symbol_placement_violations(
    symbols: Sequence[RawRecord], rules: Sequence[ArchitectureRule]
) -> list[RawRecord]:
    """AD-58: a class of a named kind below `source` must be defined in an allowed module."""
    violations: list[RawRecord] = []
    for rule in rules:
        if not isinstance(rule, SymbolPlacementRule):
            continue
        kinds = frozenset(kind.value for kind in rule.class_kinds)
        for item in symbols:
            data = item["data"]
            if item["kind"] != "class" or data.get("class_kind") not in kinds:
                continue
            qualname = data["qualified_name"]
            module = data["module"]
            if (
                not in_scope(qualname, rule.source)
                or any(in_scope(module, allowed) for allowed in rule.allowed_sources)
                or module in rule.exact_sources
            ):
                continue
            violations.append(
                classified(
                    item_id=stable_id("VIO", rule.id, item["id"]),
                    evidence_class=EvidenceClass.VIOLATION,
                    area="type_architecture",
                    kind=rule.kind,
                    title=f"{qualname} ({data['class_kind']}) is defined outside an allowed module",
                    subjects=[qualname, module],
                    evidence_ids=item["evidence_ids"],
                    rule_ids=[rule.id],
                    fact_ids=[item["id"]],
                    data={
                        "source": rule.source,
                        "class_kind": data["class_kind"],
                        "module": module,
                        "qualified_name": qualname,
                    },
                )
            )
    return sorted(violations, key=lambda item: item["id"])


_BROAD_BOUNDARY_TYPES: Final = ("dict", "Dict", "object")


def _is_broad_boundary_type(annotation: str) -> bool:
    """A bare `dict`/`Dict`/`object`, or a `dict[...]`/`Dict[...]` generic (AD-58).

    Restricted to what the annotation string alone decides: a generic other than `dict`, a
    dotted name, a forward-reference string and a missing annotation all stay silent rather
    than guess. A bare named type is decided separately, by `_resolve_named_type` (AD-63).
    """
    return annotation in _BROAD_BOUNDARY_TYPES or annotation.startswith(("dict[", "Dict["))


_EXEMPT_CLASS_KINDS: Final = frozenset({"enum", "pydantic_model"})


def _resolve_named_type(
    annotation: str,
    module: str,
    imports_by_binding: dict[tuple[str, str], RecordData],
    classes_by_location: dict[tuple[str, str], RecordData],
) -> tuple[str, str] | None:
    """Resolve a bare annotation name to the module and name where it is actually defined.

    Reuses the same `binding`/`origin_definition` fields `imports` already carries for
    `interface_boundary` (AD-9), so a `from ir import ObservationResult` import lets an
    `ObservationResult` annotation resolve the way the import itself would. Only a single bare
    identifier is attempted, never a dotted name, a subscripted generic or a forward-reference
    string: those stay unresolved exactly as AD-58 left them. A builtin needs no import and
    defines no symbol of its own, so it resolves to nothing here and stays silent rather than
    being matched against a fixed list that would drift from what Python actually ships.
    """
    if not annotation.isidentifier():
        return None
    imported = imports_by_binding.get((module, annotation))
    if imported is not None:
        origin = imported["origin_definition"]
        # A bare `import pkg as name` binds a module, not a name; nonsensical as a type.
        if imported["symbol"] is None or not origin:
            return None
        origin_module, _, origin_name = origin.rpartition(".")
        return origin_module, origin_name
    if (module, annotation) in classes_by_location:
        return module, annotation
    return None


def _boundary_type_indexes(
    symbols: Sequence[RawRecord], imports: Sequence[RawRecord]
) -> tuple[dict[tuple[str, str], RecordData], dict[tuple[str, str], RecordData]]:
    """Index `imports` by (module, local binding) and top-level classes by (module, name).

    Both are `_resolve_named_type`'s own lookups, built once per call instead of once per
    function checked: `boundary_types` may inspect many facade functions below one `source`.
    """
    imports_by_binding = {
        (data["source_module"], data["binding"]): data
        for data in (item["data"] for item in imports)
    }
    classes_by_location = {
        (data["module"], data["name"]): data
        for item in symbols
        for data in [item["data"]]
        # A nested class is never what a module-level annotation's bare name resolves to.
        if item["kind"] == "class" and data.get("parent") is None
    }
    return imports_by_binding, classes_by_location


def _boundary_type_reason(
    annotation: str,
    module: str,
    contract: ArchitectureContract,
    exports_by_module: dict[str, frozenset[str]],
    imports_by_binding: dict[tuple[str, str], RecordData],
    classes_by_location: dict[tuple[str, str], RecordData],
) -> str | None:
    """Why one annotation violates `boundary_types`, or None when it does not (AD-58, AD-63)."""
    if _is_broad_boundary_type(annotation):
        return "instead of a typed model"
    resolved = _resolve_named_type(annotation, module, imports_by_binding, classes_by_location)
    if resolved is None:
        return None
    origin_module, origin_name = resolved
    origin_symbol = classes_by_location.get(resolved)
    class_kind = origin_symbol["class_kind"] if origin_symbol else None
    origin_component = contract.component_for(origin_module)
    if (
        class_kind in _EXEMPT_CLASS_KINDS
        or origin_component is None
        or _facade_covers(origin_module, origin_name, origin_component, exports_by_module)
    ):
        return None
    return f"which {origin_component.label} does not declare"


def _facade_positions(
    item: RawRecord,
    rule: BoundaryTypesRule,
    contract: ArchitectureContract,
    exports_by_module: dict[str, frozenset[str]],
) -> tuple[str, str, list[tuple[str, str]]] | None:
    """The (module, qualified name, annotated positions) of one function `rule` must check, or
    None when it is not a function, out of scope, exempted, or not itself a function
    `component.public` covers -- a naming convention used to guess at that last one (AD-63).
    """
    data = item["data"]
    if item["kind"] != "function" or data.get("symbol_category") != "function":
        return None
    module, name = data["module"], data["name"]
    component = contract.component_for(module)
    if (
        not in_scope(module, rule.source)
        or any(in_scope(module, allowed) for allowed in rule.allowed_sources)
        or module in rule.exact_sources
        or component is None
        or not _facade_covers(module, name, component, exports_by_module)
    ):
        return None
    positions = [
        (parameter["name"], parameter["annotation"])
        for parameter in data["parameters"]
        if parameter["annotation"]
    ]
    if data["returns"]:
        positions.append(("return", data["returns"]))
    return module, data["qualified_name"], positions


def _boundary_types_violations(
    symbols: Sequence[RawRecord],
    imports: Sequence[RawRecord],
    contract: ArchitectureContract,
    exports_by_module: dict[str, frozenset[str]],
) -> list[RawRecord]:
    """AD-58, amended by AD-63: a component's declared facade function takes and returns no
    bare `dict`/`object`, and no named type outside a builtin, an enum, a Pydantic model, or a
    type some component -- whichever one actually owns it -- already declares public.

    Only a function `component.public` itself covers is inspected: an internal helper below
    `source` that the contract never promised as facade is not a claim about the boundary, so
    it is not this rule's business (issue #44). `allowed_sources`/`exact_sources` still exempt
    a module the way `forbidden_construct` does (AD-49), for a component such as `ir` whose
    facade legitimately narrows an untyped boundary with a bare `object`.
    """
    rules = [rule for rule in contract.rules if isinstance(rule, BoundaryTypesRule)]
    if not rules:
        return []
    imports_by_binding, classes_by_location = _boundary_type_indexes(symbols, imports)
    violations: list[RawRecord] = []
    for rule in rules:
        for item in symbols:
            found = _facade_positions(item, rule, contract, exports_by_module)
            if found is None:
                continue
            module, qualname, positions = found
            for position, annotation in positions:
                reason = _boundary_type_reason(
                    annotation,
                    module,
                    contract,
                    exports_by_module,
                    imports_by_binding,
                    classes_by_location,
                )
                if reason is None:
                    continue
                verb = "returns" if position == "return" else f"takes {position} as"
                violations.append(
                    classified(
                        item_id=stable_id("VIO", rule.id, item["id"], position),
                        evidence_class=EvidenceClass.VIOLATION,
                        area="type_architecture",
                        kind=rule.kind,
                        title=f"{qualname} {verb} {annotation} {reason}",
                        subjects=[qualname, module],
                        evidence_ids=item["evidence_ids"],
                        rule_ids=[rule.id],
                        fact_ids=[item["id"]],
                        data={
                            "source": rule.source,
                            "qualified_name": qualname,
                            "module": module,
                            "position": position,
                            "annotation": annotation,
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
    symbols: Sequence[RawRecord],
    blank_modules: frozenset[str],
    contract: ArchitectureContract,
    exports_by_module: dict[str, frozenset[str]],
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
            *_interface_violations(imports, contract, exports_by_module, forbidden_rejected_ids),
            *_sibling_violations(imports, contract.rules),
            *_symbol_placement_violations(symbols, contract.rules),
            *_boundary_types_violations(symbols, imports, contract, exports_by_module),
        ],
        key=lambda item: item["id"],
    )
