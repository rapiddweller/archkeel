# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Evaluate declared class-A contract rules against scanner records."""

from __future__ import annotations

import ast
import builtins
from collections import defaultdict
from collections.abc import Iterator, Sequence
from collections.abc import Set as AbstractSet
from typing import Final, Literal, NamedTuple, TypeAlias, assert_never

from archkeel.ir.model import (
    AllowedDependencyRule,
    ArchitectureContract,
    ArchitectureRule,
    BoundaryTypesRule,
    CompleteAssignmentRule,
    CompleteExternalScopeRule,
    CompleteRequiresRule,
    ContractComponent,
    ContractDeclarations,
    EvidenceClass,
    ExternalDependencyScopeRule,
    ForbiddenConstructKind,
    ForbiddenConstructRule,
    ForbiddenDependencyRule,
    InterfaceBoundaryRule,
    NoComponentCyclesRule,
    RootLayoutRule,
    SiblingIsolationRule,
    SymbolPlacementRule,
    in_scope,
    package_owners,
    stable_id,
)
from archkeel.ir.profiles import DeclarationField, Profile

from .graph import strongly_connected_components
from .records import RawEvidence, RawRecord, RecordData, classified

# AD-97: an import either decides a symbol rule or, when the scan cannot see which names it
# uses (a Dart import without `show`), leaves it undecided -- never a pass, never a violation.
_Verdict: TypeAlias = Literal["violation", "allowed", "undecided"]
UncertainReexportOrigins: TypeAlias = dict[str, frozenset[str]]
FacadeEntry: TypeAlias = tuple[str, str, str, bool]
DeclaredFacade: TypeAlias = tuple[str, str, list[tuple[str, str]], str, tuple[FacadeEntry, ...]]


def _forbidden_dependency_verdicts(
    imports: Sequence[RawRecord],
    rules: Sequence[ArchitectureRule],
    components: tuple[tuple[str, tuple[str, ...]], ...],
    source_modules: frozenset[str] | None = None,
) -> Iterator[tuple[ForbiddenDependencyRule, RawRecord, _Verdict]]:
    """Yield each (rule, import) pair whose modules a forbidden_dependency rule names.

    A rule without `target_symbol` rejects every such import. One with it rejects the import
    naming that symbol, lets one naming another pass, and cannot decide one whose names the
    scan does not know.
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
            if source_modules is not None and item["data"]["source_module"] not in source_modules:
                continue
            data = item["data"]
            if not any(in_scope(data["source_module"], package) for package in sources) or not any(
                in_scope(data["target_module"], package) for package in targets
            ):
                continue
            if data["source_module"] in allowed_sources:
                continue
            if data["under_type_checking"] and not rule.include_type_checking:
                continue
            if rule.target_symbol is None or data["symbol"] == rule.target_symbol:
                yield rule, item, "violation"
            else:
                yield rule, item, "allowed" if data["symbols_known"] else "undecided"


def _forbidden_dependency_matches(
    imports: Sequence[RawRecord],
    rules: Sequence[ArchitectureRule],
    components: tuple[tuple[str, tuple[str, ...]], ...],
    source_modules: frozenset[str] | None = None,
) -> Iterator[tuple[ForbiddenDependencyRule, RawRecord]]:
    """Yield each (rule, import) pair a forbidden_dependency rule rejects.

    AD-18: interface_boundary reuses this to skip an import a forbidden rule already
    rejects, instead of a second matcher that could drift from this one (SPOT).
    """
    for rule, item, verdict in _forbidden_dependency_verdicts(
        imports, rules, components, source_modules
    ):
        if verdict == "violation":
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
    signals: Sequence[RawRecord],
    rules: Sequence[ArchitectureRule],
    source_modules: frozenset[str] | None = None,
) -> list[RawRecord]:
    violations: list[RawRecord] = []
    for rule in rules:
        if not isinstance(rule, ForbiddenConstructRule):
            continue
        for item in signals:
            construct = _CONSTRUCT_SIGNALS.get(item["kind"])
            owner = item["data"]["owner"]
            scope = owner.split(":", 1)[0]
            belongs_to_source = source_modules is None or any(
                owner == module or owner.startswith(f"{module}.") for module in source_modules
            )
            if (
                not belongs_to_source
                or construct is None
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
    imports: Sequence[RawRecord],
    rules: Sequence[ArchitectureRule],
    source_modules: frozenset[str] | None = None,
) -> list[RawRecord]:
    violations: list[RawRecord] = []
    for rule in rules:
        if not isinstance(rule, ExternalDependencyScopeRule):
            continue
        for item in imports:
            data = item["data"]
            source_module = data["source_module"]
            if (
                (source_modules is not None and source_module not in source_modules)
                or not in_scope(data["target_module"], rule.dependency)
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


def _external_completeness_violations(
    imports: Sequence[RawRecord],
    modules: Sequence[RawRecord],
    rules: Sequence[ArchitectureRule],
    standard_library: frozenset[str],
    source_modules: frozenset[str] | None = None,
) -> list[RawRecord]:
    """AD-28: an import no rule names is undecided, not harmless.

    AD-97: the exempt standard library is the profile's own, so a Dart scan exempts `dart:`
    and never Python's module names.
    """
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
            if source_modules is not None and data["source_module"] not in source_modules:
                continue
            root = target.split(".")[0]
            if root in internal_roots or root in standard_library:
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


def _root_layout_violations(
    packages: Sequence[RawRecord], modules: Sequence[RawRecord], rules: Sequence[ArchitectureRule]
) -> list[RawRecord]:
    violations: list[RawRecord] = []
    observed = [*packages, *modules]
    child_records: dict[str, RawRecord] = {}
    for item in modules:
        qualified_name = item["data"].get("qualified_name")
        package = item["data"].get("package")
        if isinstance(package, str):
            child_records.setdefault(package, item)
        if isinstance(qualified_name, str):
            child_records[qualified_name] = item
    for item in packages:
        qualified_name = item["data"].get("qualified_name")
        if isinstance(qualified_name, str):
            child_records.setdefault(qualified_name, item)
    for rule in rules:
        if not isinstance(rule, RootLayoutRule):
            continue
        root_parts = rule.root.split(".")
        children = sorted(
            {
                name
                for item in observed
                if isinstance(name := item["data"].get("qualified_name"), str)
                and name != rule.root
                and in_scope(name, rule.root)
                and len(name.split(".")) == len(root_parts) + 1
            }
        )
        for child in children:
            if child in rule.allowed_children:
                continue
            item = child_records[child]
            violations.append(
                classified(
                    item_id=stable_id("VIO", rule.id, child),
                    evidence_class=EvidenceClass.VIOLATION,
                    area="module_topology",
                    kind=rule.kind,
                    title=f"{child} is not an allowed child of {rule.root}",
                    subjects=[child],
                    evidence_ids=item["evidence_ids"],
                    rule_ids=[rule.id],
                    fact_ids=[item["id"]],
                    data={
                        "root": rule.root,
                        "child": child,
                        "allowed_children": sorted(rule.allowed_children),
                    },
                )
            )
    return sorted(violations, key=lambda item: item["id"])


def _module_placement_violations(
    modules: Sequence[RawRecord], contract: ArchitectureContract
) -> list[RawRecord]:
    """Keep ownership and physical placement separate (issue #91)."""
    violations: list[RawRecord] = []
    for component in contract.components:
        if component.namespace is None:
            continue
        for item in modules:
            module = item["data"]["qualified_name"]
            if contract.component_for(module) is not component or in_scope(
                module, component.namespace
            ):
                continue
            violations.append(
                classified(
                    item_id=stable_id("VIO", "module.placement", component.label, module),
                    evidence_class=EvidenceClass.VIOLATION,
                    area="components",
                    kind="module.placement",
                    title=(
                        f"{module} belongs to {component.label} but is outside "
                        f"{component.namespace}"
                    ),
                    subjects=[module, component.namespace],
                    evidence_ids=item["evidence_ids"],
                    # The component declaration is the typed contract fact that owns this
                    # derived placement restriction; no second rule namespace is needed.
                    rule_ids=[component.id],
                    fact_ids=[item["id"]],
                    data={
                        "module": module,
                        "component": component.label,
                        "namespace": component.namespace,
                    },
                )
            )
    return sorted(violations, key=lambda item: item["id"])


def _cycle_rules(
    contract: ArchitectureContract, level: Literal["module"] | None
) -> list[NoComponentCyclesRule]:
    return [
        rule
        for rule in contract.rules
        if isinstance(rule, NoComponentCyclesRule) and rule.level == level
    ]


def _component_cycle_violations(
    imports: Sequence[RawRecord], contract: ArchitectureContract
) -> list[RawRecord]:
    rules = _cycle_rules(contract, None)
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
            # AD-98: a scope selects the cycles that touch one of its components.
            if rule.components is None or any(label in rule.components for label in members)
        )
    return sorted(violations, key=lambda item: item["id"])


def _module_cycle_violations(
    module_cycles: Sequence[RawRecord],
    imports: Sequence[RawRecord],
    contract: ArchitectureContract,
    source_modules: frozenset[str] | None = None,
) -> list[RawRecord]:
    """One violation per module SCC the report measures, when it touches the rule's scope.

    AD-98: the rule judges the `module_scc` records themselves, so its verdict and the
    report's cycle measurement are one graph. Every import between two members closes a
    cycle, because inside an SCC each edge's target reaches its source again; those imports
    are the violation's facts and their source lines its evidence.
    """
    violations: list[RawRecord] = []
    for rule in _cycle_rules(contract, "module"):
        scope = (
            None
            if rule.components is None
            else [
                package
                for component in contract.components
                if component.label in rule.components
                for package in component.packages
            ]
        )
        for cycle in module_cycles:
            members: list[str] = cycle["data"]["members"]
            if source_modules is not None and not any(
                member in source_modules for member in members
            ):
                continue
            if scope is not None and not any(
                in_scope(member, package) for member in members for package in scope
            ):
                continue
            member_set = set(members)
            closing = [
                item
                for item in imports
                if item["data"]["source_module"] in member_set
                and item["data"]["target_module"] in member_set
                and item["data"]["source_module"] != item["data"]["target_module"]
            ]
            edges = sorted(
                {(item["data"]["source_module"], item["data"]["target_module"]) for item in closing}
            )
            violations.append(
                classified(
                    item_id=stable_id("VIO", rule.id, *members),
                    evidence_class=EvidenceClass.VIOLATION,
                    area="cycles",
                    kind="module_cycle",
                    title=f"Module cycle: {' ↔ '.join(members)}",
                    subjects=members,
                    evidence_ids=[key for item in closing for key in item["evidence_ids"]],
                    rule_ids=[rule.id],
                    fact_ids=[item["id"] for item in closing],
                    data={"members": members, "edges": [list(edge) for edge in edges]},
                )
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


def _interface_verdict(
    data: RecordData,
    target: ContractComponent,
    exports_by_module: dict[str, frozenset[str]],
    exporting: frozenset[str],
) -> _Verdict:
    """Decide one cross-component import against the target's declared interface.

    An import naming its symbols is decided exactly as it always was. One that names none
    (AD-97) is allowed when its module is public, and a violation only when nothing the target
    library offers can be public: no `module:name` entry and no `export` that could pass one on.
    """
    if data["symbols_known"]:
        return "allowed" if _interface_allows(data, target, exports_by_module) else "violation"
    module = data["target_module"]
    public = target.public or ()
    if module in public:
        return "allowed"
    prefix = f"{module}:"
    if module in exporting or any(entry[: len(prefix)] == prefix for entry in public):
        return "undecided"
    return "violation"


_InterfaceVerdict: TypeAlias = tuple[
    InterfaceBoundaryRule, RawRecord, ContractComponent, ContractComponent, _Verdict
]


def _interface_verdicts(
    imports: Sequence[RawRecord],
    contract: ArchitectureContract,
    exports_by_module: dict[str, frozenset[str]],
    forbidden_rejected_ids: frozenset[str],
    source_modules: frozenset[str] | None = None,
) -> Iterator[_InterfaceVerdict]:
    """Yield every import an interface_boundary rule judges, with its verdict."""
    rules = [rule for rule in contract.rules if isinstance(rule, InterfaceBoundaryRule)]
    exporting = frozenset(
        item["data"]["source_module"] for item in imports if item["data"]["reexport"]
    )
    for rule in rules:
        for item in imports:
            data = item["data"]
            if source_modules is not None and data["source_module"] not in source_modules:
                continue
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
            ):
                continue
            verdict = _interface_verdict(data, target, exports_by_module, exporting)
            yield rule, item, source, target, verdict


def _interface_violations(
    imports: Sequence[RawRecord],
    contract: ArchitectureContract,
    exports_by_module: dict[str, frozenset[str]],
    forbidden_rejected_ids: frozenset[str],
    source_modules: frozenset[str] | None = None,
) -> list[RawRecord]:
    violations: list[RawRecord] = []
    for rule, item, source, target, verdict in _interface_verdicts(
        imports, contract, exports_by_module, forbidden_rejected_ids, source_modules
    ):
        if verdict != "violation":
            continue
        data = item["data"]
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


def _undecided_records(
    kind: str, verdicts: Sequence[tuple[ArchitectureRule, RawRecord, _Verdict]]
) -> list[RawRecord]:
    """One UNKNOWN record per rule that left an import undecided, shaped like AD-67's."""
    records: list[RawRecord] = []
    for rule_id in sorted({rule.id for rule, _, _ in verdicts}):
        judged = [(item, verdict) for rule, item, verdict in verdicts if rule.id == rule_id]
        undecided = [item for item, verdict in judged if verdict == "undecided"]
        if not undecided:
            continue
        decided = len(judged) - len(undecided)
        records.append(
            classified(
                item_id=stable_id("UNKNOWN-SYMBOLS", kind, rule_id),
                evidence_class=EvidenceClass.UNKNOWN,
                area="dependency_violations",
                kind=kind,
                title=f"{rule_id} decided {decided} of {len(judged)} imports "
                "whose used names it depends on",
                subjects=sorted({item["data"]["source_module"] for item in undecided}),
                evidence_ids=sorted({eid for item in undecided for eid in item["evidence_ids"]}),
                rule_ids=[rule_id],
                fact_ids=[item["id"] for item in undecided],
                data={
                    "positions": len(judged),
                    "decided": decided,
                    "undecided": len(undecided),
                    "reason": "The import names no symbol, so which names cross is unknown.",
                },
            )
        )
    return records


def symbol_limits(
    imports: Sequence[RawRecord],
    contract: ArchitectureContract,
    exports_by_module: dict[str, frozenset[str]],
) -> list[RawRecord]:
    """UNKNOWN records for the symbol rules an import without named symbols leaves open (AD-97).

    A Python import always names what it binds, so only a profile whose imports may not
    (Dart without `show`) produces any. It is filed in `unknowns`, where `unknown_positions`
    turns it into the UNKNOWN verdict instead of a PASS nobody earned.
    """
    components = tuple((component.label, component.packages) for component in contract.components)
    forbidden = list(_forbidden_dependency_verdicts(imports, contract.rules, components))
    rejected = frozenset(item["id"] for _, item, verdict in forbidden if verdict == "violation")
    interface = [
        (rule, item, verdict)
        for rule, item, _, _, verdict in _interface_verdicts(
            imports, contract, exports_by_module, rejected
        )
    ]
    return sorted(
        [
            *_undecided_records("dependency_symbol_limit", forbidden),
            *_undecided_records("interface_symbol_limit", interface),
        ],
        key=lambda item: item["id"],
    )


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
    if isinstance(rule, RootLayoutRule):
        return {"root": (rule.root,)}
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
    imports: Sequence[RawRecord],
    contract: ArchitectureContract,
    exports_by_module: dict[str, frozenset[str]],
    uncertain_reexport_origins: UncertainReexportOrigins,
    scanned_modules: set[str],
    stable_bindings_by_module: dict[str, frozenset[str]],
    source_modules: frozenset[str] | None = None,
) -> frozenset[str]:
    """Modules carrying at least one function `rule` actually inspects (issue #56).

    `source` matching a scanned module used to be enough: every non-underscore, module-level
    function under it was a subject. AD-63 reads the declared facade instead, so a component
    whose `public` is `None`, or whose `public` never covers a function under `source`, gives
    the rule zero functions to check -- a scanned module is no longer the same thing as a
    decided subject for this one rule kind, and `rule_subject_failures` has to see that instead
    of reading an empty result as a clean pass.
    """
    function_subjects = frozenset(
        module
        for item in symbols
        if (
            found := _facade_positions(
                item,
                rule,
                contract,
                exports_by_module,
                imports,
                uncertain_reexport_origins,
            )
        )
        is not None
        for module in (found[0],)
        if source_modules is None or module in source_modules
    )
    route_subjects = frozenset(
        module
        for record in _unresolved_public_alias_routes(
            rule,
            symbols,
            imports,
            contract,
            exports_by_module,
            uncertain_reexport_origins,
            scanned_modules,
            stable_bindings_by_module,
            source_modules,
        )
        if "module" in record["data"]
        and isinstance((module := record["data"]["module"]), str)
        and (source_modules is None or module in source_modules)
    )
    return function_subjects | route_subjects


def _planned_subject_modules(contract: ArchitectureContract) -> frozenset[str]:
    """Let declared target work explain a rule scope before the module exists (#79)."""
    return frozenset(
        module
        for component in contract.components
        for entry in component.planned or ()
        for module in (entry.partition(":")[0],)
    )


def rule_subject_failures(
    rules: Sequence[ArchitectureRule],
    module_names: set[str],
    *,
    target_module_names: set[str] | None = None,
    symbols: Sequence[RawRecord] = (),
    imports: Sequence[RawRecord] = (),
    contract: ArchitectureContract | None = None,
    exports_by_module: dict[str, frozenset[str]] | None = None,
    uncertain_reexport_origins: UncertainReexportOrigins | None = None,
    stable_bindings_by_module: dict[str, frozenset[str]] | None = None,
    sdk_libraries: frozenset[str] = frozenset(),
    source_modules: frozenset[str] | None = None,
) -> list[RawRecord]:
    """Flag scopes with neither observed subjects nor explicitly declared target work.

    For `boundary_types`, a public facade function or matching planned entry is a subject. A rule
    that can only pass by finding neither must report UNKNOWN, not PASS (AD-63, AD-79).
    A `forbidden_dependency` target naming one of the profile's SDK libraries is a subject no
    scan can list as a module, yet an import of it is observed like any other (AD-97).
    """
    planned_subjects = _planned_subject_modules(contract) if contract is not None else frozenset()
    rule_failures: list[RawRecord] = []
    for rule in rules:
        scopes = rule_scopes(rule)
        if isinstance(rule, ForbiddenDependencyRule) and rule.target in sdk_libraries:
            scopes = {"source": scopes["source"]}
        source_subjects: AbstractSet[str] = module_names | planned_subjects
        target_subjects: AbstractSet[str] = (target_module_names or module_names) | planned_subjects
        facade_scoped = False
        if isinstance(rule, BoundaryTypesRule) and contract is not None:
            source_subjects = _boundary_type_subject_modules(
                rule,
                symbols,
                imports,
                contract,
                exports_by_module or {},
                uncertain_reexport_origins or {},
                module_names,
                stable_bindings_by_module or {},
                source_modules,
            )
            source_subjects = source_subjects | planned_subjects
            facade_scoped = True
        matches = {
            side: sum(
                any(in_scope(module, scope) for scope in side_scopes)
                for module in (target_subjects if side == "target" else source_subjects)
            )
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


def profile_failures(contract: ArchitectureContract, profile: Profile) -> list[RawRecord]:
    """One coverage failure per contract item the scanning profile cannot decide (AD-97).

    A rule the profile never evaluates would otherwise read as a clean pass; a declaration or
    budget it cannot observe would read as empty. Both gate the run with exit 2 instead.
    """
    declarations = contract.declarations or ContractDeclarations()
    declared: dict[DeclarationField, bool] = {
        "context_roots": bool(declarations.context_roots),
        "facade_budgets": bool(declarations.facade_budgets),
        "coupling_budgets": bool(declarations.coupling_budgets),
    }
    items = [
        *(
            (rule.id, [rule.id], f"rule kind {rule.kind}")
            for rule in contract.rules
            if rule.kind in profile.unsupported_rules
        ),
        *(
            (f"declarations.{name}", [], f"declarations.{name}")
            for name in sorted(profile.unsupported_declarations)
            if declared[name]
        ),
        *(
            (f"declarations.measurement_budgets.{budget.name}", [], f"budget {budget.name}")
            for budget in declarations.measurement_budgets
            if budget.name in profile.unmeasured
        ),
    ]
    return [
        classified(
            item_id=stable_id("UNKNOWN-PROFILE", subject),
            evidence_class=EvidenceClass.UNKNOWN,
            area="analysis_coverage",
            kind="rule-unsupported-by-profile",
            title=f"{subject}: {what} is not supported by the {profile.analyzer} profile",
            subjects=[subject],
            rule_ids=rule_ids,
            data={"analyzer": profile.analyzer},
        )
        for subject, rule_ids, what in items
    ]


def _sibling_violations(
    imports: Sequence[RawRecord],
    rules: Sequence[ArchitectureRule],
    source_modules: frozenset[str] | None = None,
) -> list[RawRecord]:
    """AD-25: peers of one declared set reach shared modules, never each other."""
    violations: list[RawRecord] = []
    for rule in rules:
        if not isinstance(rule, SiblingIsolationRule):
            continue
        for item in imports:
            data = item["data"]
            if source_modules is not None and data["source_module"] not in source_modules:
                continue
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
    symbols: Sequence[RawRecord],
    rules: Sequence[ArchitectureRule],
    source_modules: frozenset[str] | None = None,
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
                (source_modules is not None and module not in source_modules)
                or not in_scope(qualname, rule.source)
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
    than guess. A bare named type is decided separately, by `resolve_named_type` (AD-63).
    """
    return annotation in _BROAD_BOUNDARY_TYPES or annotation.startswith(("dict[", "Dict["))


_EXEMPT_CLASS_KINDS: Final = frozenset({"enum", "pydantic_model"})

# Issue #9 names a builtin as an acceptable boundary type, and a builtin needs no import and
# defines no symbol of its own, so `resolve_named_type` returns nothing for one. The set comes
# from the running interpreter rather than a list kept here, the way `resolve.py` and `calls.py`
# already answer the same question, so one repository holds one answer to what a builtin is.
_BUILTIN_NAMES: Final = frozenset(dir(builtins))

# Why a position stayed undecided, in the order the limit record reports them (AD-67).
# `ambiguous_binding` (AD-74) sits next to `unresolved_name`: both are bare names that failed
# to resolve, but one failed because nothing defines it and the other because two records do --
# a reader who sees only the count needs the two kept apart to tell "unreadable annotation"
# from "this name is bound twice".
_UNDECIDABLE_KINDS: Final = (
    "missing_annotation",
    "forward_reference",
    "dotted_name",
    "generic",
    "union",
    "ambiguous_binding",
    "ambiguous_facade",
    "unresolved_name",
    "external_type",
    "nested_type",
    "other",
)


class _Position(NamedTuple):
    """The one reading of an annotated position: the named types it resolves to, plus the
    `boundary_types` rule's verdict on them -- a violation reason, an undecidable kind, or
    neither.

    Neither is a decided pass. AD-63 answered all three with `None`, so a position the rule
    could not decide was indistinguishable from one it decided clean, and the rule's verdict
    read `no violation == probably fine` where the rest of the tool reads PASS, VIOLATION or
    UNKNOWN (AD-26). Naming the undecidable kind is what lets the rule report its own
    denominator instead of staying silent (AD-67).

    `resolved` is what `facade_types` (AD-65) reads off this same walk: a type reaches a
    component's boundary by being named in a signature, whether or not the rule's own
    exemptions (a builtin, an enum, an already-declared type) let it pass, so it is filled in
    on every branch that resolves a name and left empty on every branch that does not -- one
    walk of the annotation feeding both readers instead of each re-deriving it (AD-69's own
    Limit, closed for good).
    """

    violation: str | None = None
    undecidable: str | None = None
    resolved: tuple[tuple[str, str], ...] = ()
    path: tuple[str, ...] = ()
    nested_annotation: str | None = None
    violations: tuple[tuple[str, tuple[str, ...], str | None], ...] = ()


# A container whose declared element type is the whole of what actually crosses the boundary
# (AD-67). `dict`/`Dict` are absent because AD-58 already reports a `dict[...]` as broad, and
# `Mapping` because whether a mapping is that same broad container is a reading AD-67 leaves open.
_COLLECTION_CONTAINERS: Final = frozenset(
    {
        "list",
        "List",
        "set",
        "Set",
        "frozenset",
        "FrozenSet",
        "tuple",
        "Tuple",
        "Sequence",
        "MutableSequence",
        "Iterable",
        "Iterator",
        "Collection",
        "AbstractSet",
    }
)


def _split_type_parameters(inner: str) -> list[str] | None:
    """Split one subscript's parameters on its top-level commas.

    None when the brackets do not balance, which is how `Sequence[int] | list[str]` is told
    apart from a single subscript: both end in `]`, only one of them is one (AD-67).
    """
    parameters: list[str] = []
    current = ""
    depth = 0
    for character in inner:
        if character == "[":
            depth += 1
        elif character == "]":
            depth -= 1
            if depth < 0:
                return None
        if character == "," and depth == 0:
            parameters.append(current.strip())
            current = ""
        else:
            current += character
    if depth:
        return None
    parameters.append(current.strip())
    return parameters


def _typing_module_binding(module: str, binding: str, imports_by_binding: BindingIndex) -> bool:
    imported = imports_by_binding.get((module, binding))
    return (
        isinstance(imported, dict)
        and imported["target_module"] == "typing"
        and imported["symbol"] is None
    )


def _typing_dict_verdict(
    annotation: str,
    module: str,
    imports_by_binding: BindingIndex,
    classes_by_location: BindingIndex,
) -> _Position | None:
    try:
        expression = ast.parse(annotation, mode="eval").body
    except SyntaxError:
        return None
    if not isinstance(expression, ast.Subscript):
        return None
    head = expression.value
    if isinstance(head, ast.Name):
        key = (module, head.id)
        imported = imports_by_binding.get(key)
        if (
            not isinstance(imported, dict)
            or imported["target_module"] != "typing"
            or imported["symbol"] != "Dict"
        ):
            return None
    elif (
        isinstance(head, ast.Attribute) and head.attr == "Dict" and isinstance(head.value, ast.Name)
    ):
        key = (module, head.value.id)
        if not _typing_module_binding(module, head.value.id, imports_by_binding):
            return None
    else:
        return None
    if _binding_is_ambiguous(key, imports_by_binding, classes_by_location):
        return _Position(undecidable="ambiguous_binding")
    return _Position(violation="instead of a typed model")


def _typing_wrapper_inner(
    annotation: str,
    module: str,
    imports_by_binding: BindingIndex,
    classes_by_location: BindingIndex,
    wrapper: str,
) -> str | tuple[str, ...] | None:
    """Return T for a statically bound typing wrapper such as Annotated[T, metadata]."""
    try:
        expression = ast.parse(annotation, mode="eval").body
    except SyntaxError:
        return None
    if not isinstance(expression, ast.Subscript):
        return None
    head = expression.value
    if isinstance(head, ast.Name):
        key = (module, head.id)
        if _binding_is_ambiguous(key, imports_by_binding, classes_by_location):
            return None
        imported = imports_by_binding.get(key)
        if not isinstance(imported, dict) or imported["target_module"] != "typing":
            return None
        if imported["symbol"] != wrapper:
            return None
    elif isinstance(head, ast.Attribute) and isinstance(head.value, ast.Name):
        key = (module, head.value.id)
        if _binding_is_ambiguous(key, imports_by_binding, classes_by_location):
            return None
        if head.attr != wrapper or not _typing_module_binding(
            module, head.value.id, imports_by_binding
        ):
            return None
    else:
        return None
    parameters = (
        list(expression.slice.elts)
        if isinstance(expression.slice, ast.Tuple)
        else [expression.slice]
    )
    if wrapper == "Annotated" and len(parameters) >= 2:
        return ast.unparse(parameters[0])
    if wrapper == "Literal" and parameters:
        names: list[str] = []
        for value in parameters:
            if isinstance(value, ast.Constant) and isinstance(
                value.value, (str, int, bool, type(None))
            ):
                continue
            if isinstance(value, ast.Name):
                names.append(value.id)
                continue
            if isinstance(value, ast.Attribute):
                names.append(ast.unparse(value))
                continue
            return None
        return tuple(names)
    return None


def _collection_parameters(
    annotation: str,
    module: str,
    imports_by_binding: BindingIndex,
) -> list[str] | None:
    """The type parameters of `Container[...]` when the container is a known collection.

    None when the annotation is not exactly one such subscript, so dotted containers without a
    proven `typing` import, a union around one and a mapping all stay where they were. The
    `...` of `tuple[X, ...]` is an arity, not a type, and is dropped (AD-67).
    """
    head, bracket, rest = annotation.partition("[")
    if "." in head:
        binding = annotation.split(".", 1)[0]
        container = head[len(binding) + 1 :]
        if container not in _COLLECTION_CONTAINERS or not _typing_module_binding(
            module, binding, imports_by_binding
        ):
            return None
    else:
        container = head
        imported = imports_by_binding.get((module, container))
        if container not in _COLLECTION_CONTAINERS and (
            not isinstance(imported, dict)
            or imported["target_module"] != "typing"
            or imported["symbol"] not in _COLLECTION_CONTAINERS
        ):
            return None
        if isinstance(imported, dict) and imported["target_module"] == "typing":
            container = imported["symbol"] or container
    if not bracket or not rest.endswith("]") or container not in _COLLECTION_CONTAINERS:
        return None
    parameters = _split_type_parameters(rest[:-1])
    if parameters is None:
        return None
    return [parameter for parameter in parameters if parameter != "..."]


def _unresolvable_shape(annotation: str) -> str:
    """Name why an annotation that is not one bare identifier cannot be decided (AD-67)."""
    head = annotation.split("[", 1)[0]
    if "." in head:
        return "dotted_name"
    if "[" in annotation:
        return "generic"
    if "|" in annotation:
        return "union"
    return "other"


def _union_parameters(
    annotation: str,
    module: str,
    imports_by_binding: BindingIndex,
) -> list[str] | None:
    """Return members only for syntactically valid standard union annotations."""
    try:
        expression = ast.parse(annotation, mode="eval").body
    except SyntaxError:
        return None
    if isinstance(expression, ast.BinOp) and isinstance(expression.op, ast.BitOr):
        return [ast.unparse(expression.left), ast.unparse(expression.right)]
    if not isinstance(expression, ast.Subscript):
        return None
    head = expression.value
    if isinstance(head, ast.Name):
        name = head.id
        imported = imports_by_binding.get((module, name))
        if (
            not isinstance(imported, dict)
            or imported["target_module"] != "typing"
            or imported["symbol"] not in {"Union", "Optional"}
        ):
            return None
        name = imported["symbol"]
    elif isinstance(head, ast.Attribute) and isinstance(head.value, ast.Name):
        if not _typing_module_binding(module, head.value.id, imports_by_binding):
            return None
        name = head.attr
    else:
        return None
    if name not in {"Union", "Optional"}:
        return None
    members = (
        list(expression.slice.elts)
        if isinstance(expression.slice, ast.Tuple)
        else [expression.slice]
    )
    if name == "Optional":
        return [ast.unparse(members[0]), "None"] if len(members) == 1 else None
    return [ast.unparse(member) for member in members] if len(members) >= 2 else None


class _AmbiguousBinding:
    """Sentinel for a `(module, name)` key more than one distinct binding claims.

    Nothing recorded says which import or which same-named class definition is the one Python
    actually binds -- that is `boundary_type_indexes`'s whole reason to exist -- so a key with
    more than one claimant maps here instead of to whichever claimant happened to arrive last.
    """

    __slots__ = ()


_AMBIGUOUS: Final = _AmbiguousBinding()


# `boundary_type_indexes`'s own return shape: a `(module, name)` key maps to one binding target,
# or to `_AMBIGUOUS` when distinct targets or definitions claim it.
class BindingIndex(dict[tuple[str, str], RecordData | _AmbiguousBinding]):
    """Bindings plus same-owner facade evidence kept internal to type resolution."""

    def __init__(self) -> None:
        super().__init__()
        self.owner_facade_type_states: dict[tuple[str, str, str], bool] = {}


def _binding_is_ambiguous(
    key: tuple[str, str], imports_by_binding: BindingIndex, classes_by_location: BindingIndex
) -> bool:
    imported = imports_by_binding.get(key)
    local = classes_by_location.get(key)
    return (
        imported is _AMBIGUOUS
        or local is _AMBIGUOUS
        or (imported is not None and local is not None)
    )


def resolve_named_type(
    annotation: str,
    module: str,
    imports_by_binding: BindingIndex,
    classes_by_location: BindingIndex,
) -> tuple[str, str] | _AmbiguousBinding | None:
    """Resolve a bare annotation name to the module and name where it is actually defined.

    Reuses the same `binding`/`origin_definition` fields `imports` already carries for
    `interface_boundary` (AD-9), so a `from ir import ObservationResult` import lets an
    `ObservationResult` annotation resolve the way the import itself would. Only a single bare
    identifier is attempted, never a dotted name, a subscripted generic or a forward-reference
    string: those stay unresolved exactly as AD-58 left them. A builtin needs no import and
    defines no symbol of its own, so it still resolves to nothing here; what changed is that
    the caller no longer reads that nothing as silence but asks the interpreter whether the
    name is a builtin, and calls it a decided pass when it is (AD-67).

    Returns `_AMBIGUOUS` when the name has distinct bindings in `module` (imports to different
    targets, an import and a local class, or colliding local definitions), or when it resolves
    to a location two same-named class definitions both claim. The records carry no source order,
    so the caller must read that apart from an unresolved name rather than pick a claimant.
    """
    if not annotation.isidentifier():
        return None
    key = (module, annotation)
    if _binding_is_ambiguous(key, imports_by_binding, classes_by_location):
        return _AMBIGUOUS
    imported = imports_by_binding.get(key)
    class_entry = classes_by_location.get(key)
    if isinstance(imported, dict):
        origin = imported["origin_definition"]
        # A bare `import pkg as name` binds a module, not a name; nonsensical as a type.
        if imported["symbol"] is None or not origin:
            return None
        origin_module, _, origin_name = origin.rpartition(".")
        chain = imported["reexport_chain"] or [origin]
        for entry in chain:
            entry_module, _, entry_name = entry.rpartition(".")
            if _binding_is_ambiguous(
                (entry_module, entry_name), imports_by_binding, classes_by_location
            ):
                return _AMBIGUOUS
        return origin_module, origin_name
    if class_entry is not None:
        return module, annotation
    return None


def _binding_index(entries: Iterator[tuple[str, str, object, RecordData]]) -> BindingIndex:
    """Index a binding once, or mark distinct targets ambiguous regardless of input order.

    Repeating the same import target does not change a Python binding and keeps the first record.
    Separate class definitions carry separate identities even when their bodies are identical
    (AD-74).
    """
    index = BindingIndex()
    identities: dict[tuple[str, str], object] = {}
    for scope, name, identity, data in entries:
        key = (scope, name)
        if key not in index:
            index[key] = data
            identities[key] = identity
        elif identities[key] != identity:
            index[key] = _AMBIGUOUS
    return index


def boundary_type_indexes(
    symbols: Sequence[RawRecord],
    imports: Sequence[RawRecord],
    contract: ArchitectureContract | None = None,
    exports_by_module: dict[str, frozenset[str]] | None = None,
    uncertain_reexport_origins: UncertainReexportOrigins | None = None,
) -> tuple[BindingIndex, BindingIndex]:
    """Index `imports` by (module, local binding) and top-level classes by (module, name).

    Both are `resolve_named_type`'s own lookups, built once per call instead of once per
    function checked: `boundary_types` may inspect many facade functions below one `source`,
    and `public_api_exposed_types` every declared `public_api` entry.

    `symbols` and `imports` arrive sorted by each record's own content-hash id, not source
    order, so distinct definitions sharing a binding must not let arrival order decide which
    record wins. Repeating one import target is still one binding (AD-74).
    """
    imports_by_binding = _binding_index(
        (
            data["source_module"],
            data["binding"],
            (data["target_module"], data["symbol"]),
            data,
        )
        for data in (item["data"] for item in imports)
    )
    classes_by_location = _binding_index(
        (data["module"], data["name"], item["id"], data)
        for item in symbols
        for data in [item["data"]]
        # A nested class is never what a module-level annotation's bare name resolves to.
        if (item["kind"] == "class" and data.get("parent") is None)
        or item["kind"] in {"type_alias", "static_constant", "dynamic_binding"}
    )
    for item in symbols:
        data = item["data"]
        key = (data["module"], data["name"])
        if item["kind"] == "function" and (key in classes_by_location or key in imports_by_binding):
            classes_by_location[key] = _AMBIGUOUS
    if contract is not None:
        _index_owner_facade_type_states(
            imports,
            imports_by_binding,
            contract,
            exports_by_module or {},
            uncertain_reexport_origins or {},
        )
    return imports_by_binding, classes_by_location


def _index_owner_facade_type_states(
    imports: Sequence[RawRecord],
    imports_by_binding: BindingIndex,
    contract: ArchitectureContract,
    exports_by_module: dict[str, frozenset[str]],
    uncertain_reexport_origins: UncertainReexportOrigins,
) -> None:
    proven: set[tuple[str, str, str]] = set()
    uncertain: set[tuple[str, str, str]] = set()
    for item in imports:
        data = item["data"]
        module, binding = data["source_module"], data["binding"]
        owner = contract.component_for(module)
        if owner is None or not _facade_covers(module, binding, owner, exports_by_module):
            continue
        qualified_binding = f"{module}.{binding}"
        for origin in uncertain_reexport_origins.get(qualified_binding, frozenset()):
            origin_module, separator, origin_name = origin.rpartition(".")
            if separator and contract.component_for(origin_module) == owner:
                uncertain.add((owner.label, origin_module, origin_name))
        origin_definition = data.get("origin_definition")
        if (
            data.get("reexport") is True
            and imports_by_binding.get((module, binding)) is not _AMBIGUOUS
            and isinstance(origin_definition, str)
        ):
            origin_module, separator, origin_name = origin_definition.rpartition(".")
            if separator and contract.component_for(origin_module) == owner:
                proven.add((owner.label, origin_module, origin_name))
    imports_by_binding.owner_facade_type_states.update({key: False for key in uncertain})
    imports_by_binding.owner_facade_type_states.update({key: True for key in proven})


def _typing_wrapper_verdict(
    annotation: str,
    module: str,
    contract: ArchitectureContract,
    exports_by_module: dict[str, frozenset[str]],
    imports_by_binding: BindingIndex,
    classes_by_location: BindingIndex,
    *,
    enter_collections: bool,
    enter_fields: bool,
    visited: frozenset[tuple[str, str]],
    aliases_seen: frozenset[tuple[str, str]],
) -> _Position | None:
    annotated = _typing_wrapper_inner(
        annotation, module, imports_by_binding, classes_by_location, "Annotated"
    )
    if isinstance(annotated, str):
        return _boundary_type_verdict(
            annotated,
            module,
            contract,
            exports_by_module,
            imports_by_binding,
            classes_by_location,
            enter_collections=enter_collections,
            visited=visited,
            enter_fields=enter_fields,
            _aliases_seen=aliases_seen,
        )
    literal = _typing_wrapper_inner(
        annotation, module, imports_by_binding, classes_by_location, "Literal"
    )
    if not isinstance(literal, tuple):
        return None
    decided = [
        (
            name,
            _enum_member_verdict(
                name,
                module,
                contract,
                exports_by_module,
                imports_by_binding,
                classes_by_location,
                visited=visited,
                aliases_seen=aliases_seen,
            )
            or _boundary_type_verdict(
                name,
                module,
                contract,
                exports_by_module,
                imports_by_binding,
                classes_by_location,
                enter_collections=enter_collections,
                visited=visited,
                enter_fields=enter_fields,
                _aliases_seen=aliases_seen,
                _require_static_constant=True,
            ),
        )
        for name in literal
    ]
    return _combine_position_verdicts(decided)


def _boundary_type_verdict(
    annotation: str,
    module: str,
    contract: ArchitectureContract,
    exports_by_module: dict[str, frozenset[str]],
    imports_by_binding: BindingIndex,
    classes_by_location: BindingIndex,
    *,
    enter_collections: bool = True,
    visited: frozenset[tuple[str, str]] = frozenset(),
    enter_fields: bool = True,
    _aliases_seen: frozenset[tuple[str, str]] = frozenset(),
    _require_static_constant: bool = False,
) -> _Position:
    """Read one annotation for boundary_types and facade_types (AD-58, AD-69).
    Broad or undeclared types violate; builtins, enums and declared types pass. Other shapes
    report why undecidable, with bounded collection and field descent (AD-67, AD-84).
    """
    if not annotation:
        return _Position(undecidable="missing_annotation")
    wrapped = _typing_wrapper_verdict(
        annotation,
        module,
        contract,
        exports_by_module,
        imports_by_binding,
        classes_by_location,
        enter_collections=enter_collections,
        enter_fields=enter_fields,
        visited=visited,
        aliases_seen=_aliases_seen,
    )
    if wrapped is not None:
        return wrapped
    typing_dict = _typing_dict_verdict(annotation, module, imports_by_binding, classes_by_location)
    if typing_dict is not None:
        return typing_dict
    if _is_broad_boundary_type(annotation):
        return _Position(violation="instead of a typed model")
    if annotation.startswith(("'", '"')):
        return _Position(undecidable="forward_reference")
    if not annotation.isidentifier():
        return _annotation_shape_verdict(
            annotation,
            module,
            contract,
            exports_by_module,
            imports_by_binding,
            classes_by_location,
            enter_collections=enter_collections,
            visited=visited,
            enter_fields=enter_fields,
            _aliases_seen=_aliases_seen,
        )
    return _named_type_verdict(
        annotation,
        module,
        contract,
        exports_by_module,
        imports_by_binding,
        classes_by_location,
        enter_collections=enter_collections,
        enter_fields=enter_fields,
        visited=visited,
        aliases_seen=_aliases_seen,
        require_static_constant=_require_static_constant,
    )


def _enum_member_verdict(
    annotation: str,
    module: str,
    contract: ArchitectureContract,
    exports_by_module: dict[str, frozenset[str]],
    imports_by_binding: BindingIndex,
    classes_by_location: BindingIndex,
    *,
    visited: frozenset[tuple[str, str]],
    aliases_seen: frozenset[tuple[str, str]],
) -> _Position | None:
    try:
        expression = ast.parse(annotation, mode="eval").body
    except SyntaxError:
        return None
    if not isinstance(expression, ast.Attribute) or not isinstance(expression.value, ast.Name):
        return None
    base = _boundary_type_verdict(
        expression.value.id,
        module,
        contract,
        exports_by_module,
        imports_by_binding,
        classes_by_location,
        visited=visited,
        enter_fields=False,
        _aliases_seen=aliases_seen,
    )
    if base.violation is not None or base.undecidable is not None:
        return None
    enum_origin: tuple[str, str] | None = None
    for resolved in base.resolved:
        symbol = classes_by_location.get(resolved)
        if not isinstance(symbol, dict):
            return None
        if symbol.get("class_kind") == "enum":
            if enum_origin is not None:
                return None
            enum_origin = resolved
            continue
        if symbol.get("record_kind") != "type_alias":
            return None
        alias = symbol.get("alias")
        if not isinstance(alias, str):
            return None
        try:
            alias_expression = ast.parse(alias, mode="eval").body
        except SyntaxError:
            return None
        if not isinstance(alias_expression, ast.Name):
            return None
    if enum_origin is None:
        return None
    enum = classes_by_location.get(enum_origin)
    if not isinstance(enum, dict) or expression.attr not in enum.get("enum_members", ()):
        return None
    return _Position(resolved=(enum_origin,))


def _type_alias_verdict(
    symbol: RecordData | _AmbiguousBinding | None,
    resolved: tuple[str, str],
    annotation: str,
    module: str,
    contract: ArchitectureContract,
    exports_by_module: dict[str, frozenset[str]],
    imports_by_binding: BindingIndex,
    classes_by_location: BindingIndex,
    *,
    enter_collections: bool,
    enter_fields: bool,
    visited: frozenset[tuple[str, str]],
    aliases_seen: frozenset[tuple[str, str]],
) -> _Position | None:
    if not isinstance(symbol, dict) or symbol.get("record_kind") != "type_alias":
        return None
    reached: tuple[tuple[str, str], ...] = (resolved,)
    alias = symbol.get("alias")
    if resolved in aliases_seen or not isinstance(alias, str) or alias == annotation:
        return _Position(undecidable="other", resolved=reached)
    expanded = _boundary_type_verdict(
        alias,
        module,
        contract,
        exports_by_module,
        imports_by_binding,
        classes_by_location,
        enter_collections=enter_collections,
        enter_fields=enter_fields,
        visited=visited,
        _aliases_seen=aliases_seen | {resolved},
    )
    return _Position(
        violation=expanded.violation,
        undecidable=expanded.undecidable,
        resolved=tuple(sorted({*reached, *expanded.resolved})),
        path=expanded.path,
        nested_annotation=expanded.nested_annotation,
        violations=expanded.violations,
    )


def _unresolved_named_verdict(annotation: str, require_static_constant: bool) -> _Position:
    if annotation in _BUILTIN_NAMES and not require_static_constant:
        return _Position()
    if require_static_constant:
        return _Position(undecidable="other")
    return _Position(undecidable="unresolved_name")


def _is_static_literal_constant(symbol: RecordData | _AmbiguousBinding | None) -> bool:
    # A constant recorded without its value (AD-102) proves nothing; `.get` alone would read
    # the missing value as a `None` literal.
    return (
        isinstance(symbol, dict)
        and symbol.get("record_kind") == "static_constant"
        and "constant" in symbol
        and isinstance(symbol["constant"], (str, int, bool, type(None)))
    )


def _named_type_verdict(
    annotation: str,
    module: str,
    contract: ArchitectureContract,
    exports_by_module: dict[str, frozenset[str]],
    imports_by_binding: BindingIndex,
    classes_by_location: BindingIndex,
    *,
    enter_collections: bool,
    enter_fields: bool,
    visited: frozenset[tuple[str, str]],
    aliases_seen: frozenset[tuple[str, str]],
    require_static_constant: bool,
) -> _Position:
    resolved = resolve_named_type(annotation, module, imports_by_binding, classes_by_location)
    if isinstance(resolved, _AmbiguousBinding):
        # Distinct records bind this name in `module`: Python picks whichever is textually last,
        # and nothing the scanner recorded says which that is, so the position is undecidable,
        # not a guess at either candidate (AD-74).
        return _Position(undecidable="ambiguous_binding")
    if resolved is None:
        return _unresolved_named_verdict(annotation, require_static_constant)
    origin_module, origin_name = resolved
    reached: tuple[tuple[str, str], ...] = (resolved,)
    origin_symbol = classes_by_location.get(resolved)
    if require_static_constant:
        return (
            _Position()
            if _is_static_literal_constant(origin_symbol)
            else _Position(undecidable="other")
        )
    alias = _type_alias_verdict(
        origin_symbol,
        resolved,
        annotation,
        origin_module,
        contract,
        exports_by_module,
        imports_by_binding,
        classes_by_location,
        enter_collections=enter_collections,
        enter_fields=enter_fields,
        visited=visited,
        aliases_seen=aliases_seen,
    )
    if alias is not None:
        return alias
    if isinstance(origin_symbol, dict) and origin_symbol.get("record_kind") == "static_constant":
        return _Position(undecidable="other", resolved=reached)
    if isinstance(origin_symbol, dict) and origin_symbol.get("record_kind") == "dynamic_binding":
        return _Position(undecidable="other", resolved=reached)
    # `resolve_named_type` ruled out an ambiguous location; the surviving class record carries
    # `class_kind` (AD-30).
    class_kind = origin_symbol["class_kind"] if isinstance(origin_symbol, dict) else None
    if class_kind == "enum":
        return _Position(resolved=reached)
    return _owned_type_verdict(
        origin_symbol,
        origin_module,
        origin_name,
        class_kind,
        reached,
        contract,
        exports_by_module,
        imports_by_binding,
        classes_by_location,
        visited,
        aliases_seen,
    )


def _owned_type_verdict(
    origin_symbol: RecordData | _AmbiguousBinding | None,
    origin_module: str,
    origin_name: str,
    class_kind: str | None,
    reached: tuple[tuple[str, str], ...],
    contract: ArchitectureContract,
    exports_by_module: dict[str, frozenset[str]],
    imports_by_binding: BindingIndex,
    classes_by_location: BindingIndex,
    visited: frozenset[tuple[str, str]],
    aliases_seen: frozenset[tuple[str, str]],
) -> _Position:
    resolved = (origin_module, origin_name)
    origin_component = contract.component_for(origin_module)
    if origin_component is None:
        return _Position(undecidable="external_type", resolved=reached)
    owner_facade_proof = imports_by_binding.owner_facade_type_states.get(
        (origin_component.label, origin_module, origin_name)
    )
    directly_public = _facade_covers(
        origin_module, origin_name, origin_component, exports_by_module
    )
    if not directly_public and (
        owner_facade_proof is False
        or (owner_facade_proof is True and not isinstance(origin_symbol, dict))
    ):
        return _Position(undecidable="unresolved_name", resolved=reached)
    if directly_public or owner_facade_proof is True:
        if resolved in visited:
            return _Position(resolved=reached)
        fields = _declared_field_verdict(
            origin_symbol,
            origin_module,
            contract,
            exports_by_module,
            imports_by_binding,
            classes_by_location,
            visited=visited | {resolved},
            _aliases_seen=aliases_seen,
        )
        reached = tuple(sorted({*reached, *fields.resolved}))
        if fields.violation is not None:
            return _Position(
                violation=fields.violation,
                resolved=reached,
                path=fields.path,
                nested_annotation=fields.nested_annotation,
                violations=fields.violations,
            )
        if fields.undecidable is not None:
            return _Position(
                undecidable=fields.undecidable,
                resolved=reached,
                path=fields.path,
                nested_annotation=fields.nested_annotation,
                violations=fields.violations,
            )
        return _Position(resolved=reached)
    if class_kind in _EXEMPT_CLASS_KINDS:
        return _Position(resolved=reached)
    return _Position(violation=f"which {origin_component.label} does not declare", resolved=reached)


def _annotation_shape_verdict(
    annotation: str,
    module: str,
    contract: ArchitectureContract,
    exports_by_module: dict[str, frozenset[str]],
    imports_by_binding: BindingIndex,
    classes_by_location: BindingIndex,
    *,
    enter_collections: bool,
    visited: frozenset[tuple[str, str]],
    enter_fields: bool,
    _aliases_seen: frozenset[tuple[str, str]],
) -> _Position:
    """Resolve standard unions and collections recursively; leave other shapes UNKNOWN."""
    union = _union_parameters(annotation, module, imports_by_binding)
    if union is not None:
        return _combined_annotation_verdict(
            union,
            module,
            contract,
            exports_by_module,
            imports_by_binding,
            classes_by_location,
            visited=visited,
            enter_fields=enter_fields,
            _aliases_seen=_aliases_seen,
        )
    if enter_collections:
        entered = _collection_verdict(
            annotation,
            module,
            contract,
            exports_by_module,
            imports_by_binding,
            classes_by_location,
            visited=visited,
            enter_fields=enter_fields,
            _aliases_seen=_aliases_seen,
        )
        if entered is not None:
            return entered
    return _Position(undecidable=_unresolvable_shape(annotation))


def _declared_field_verdict(
    origin_symbol: RecordData | _AmbiguousBinding | None,
    module: str,
    contract: ArchitectureContract,
    exports_by_module: dict[str, frozenset[str]],
    imports_by_binding: BindingIndex,
    classes_by_location: BindingIndex,
    *,
    visited: frozenset[tuple[str, str]],
    _aliases_seen: frozenset[tuple[str, str]],
) -> _Position:
    """Inspect all owned declared model fields, stopping recursive graphs by origin."""
    if not isinstance(origin_symbol, dict) or not origin_symbol.get("fields"):
        return _Position()
    field_verdicts: list[tuple[str, str, _Position]] = []
    for field in origin_symbol["fields"]:
        if not isinstance(field, dict) or not isinstance(field.get("name"), str):
            continue
        field_verdicts.append(
            (
                field["name"],
                field.get("annotation") or "",
                _boundary_type_verdict(
                    field.get("annotation") or "",
                    module,
                    contract,
                    exports_by_module,
                    imports_by_binding,
                    classes_by_location,
                    visited=visited,
                    enter_fields=False,
                    _aliases_seen=_aliases_seen,
                ),
            )
        )
    reached: tuple[tuple[str, str], ...] = tuple(
        sorted({pair for _, _, verdict in field_verdicts for pair in verdict.resolved})
    )
    violations: list[tuple[str, tuple[str, ...], str | None]] = []
    for field_name, field_annotation, verdict in field_verdicts:
        if verdict.violations:
            violations.extend(
                (
                    reason,
                    (field_name, *path),
                    nested_annotation or field_annotation,
                )
                for reason, path, nested_annotation in verdict.violations
            )
        elif verdict.violation is not None:
            violations.append(
                (
                    verdict.violation,
                    (field_name, *verdict.path),
                    verdict.nested_annotation or field_annotation,
                )
            )
    if violations:
        reason, path, nested_annotation = violations[0]
        return _Position(
            violation=reason,
            resolved=reached,
            path=path,
            nested_annotation=nested_annotation,
            violations=tuple(violations),
        )
    for field_name, field_annotation, verdict in field_verdicts:
        if verdict.undecidable is not None:
            return _Position(
                undecidable=verdict.undecidable,
                resolved=reached,
                path=(field_name, *verdict.path),
                nested_annotation=verdict.nested_annotation or field_annotation,
            )
    return _Position(resolved=reached)


def _collection_verdict(
    annotation: str,
    module: str,
    contract: ArchitectureContract,
    exports_by_module: dict[str, frozenset[str]],
    imports_by_binding: BindingIndex,
    classes_by_location: BindingIndex,
    *,
    visited: frozenset[tuple[str, str]] = frozenset(),
    enter_fields: bool = True,
    _aliases_seen: frozenset[tuple[str, str]] = frozenset(),
) -> _Position | None:
    """Decide `Container[Name]` from its parameters, or None when it is not one (AD-67).

    The refactoring hole this closes: `execute(context: InternalContext)` was reported and
    `execute(contexts: list[InternalContext])` was silent, because a generic's parameters were
    never inspected, so moving a parameter into a list dropped the check. The container's own
    element type is the whole of what crosses the boundary, so it is decided by exactly the
    `resolve_named_type` lookup the rule already runs on a bare name -- one level in, never a
    general descent into name resolution: a nested subscript, a dotted name, a forward
    reference and a type no component owns stay undecidable, and now say so.

    A collection is only as decided as its parameters: any one of them violating makes the
    position a violation, and otherwise any one of them undecidable makes the position
    undecidable. `resolved` is the union of every parameter's own resolution regardless of
    that verdict, so a type past the first violating parameter is still one `facade_types`
    (AD-65) has to know about.
    """
    parameters = _collection_parameters(annotation, module, imports_by_binding)
    if parameters is None:
        return None
    return _combined_annotation_verdict(
        parameters,
        module,
        contract,
        exports_by_module,
        imports_by_binding,
        classes_by_location,
        visited=visited,
        enter_fields=enter_fields,
        _aliases_seen=_aliases_seen,
    )


def _combined_annotation_verdict(
    parameters: list[str],
    module: str,
    contract: ArchitectureContract,
    exports_by_module: dict[str, frozenset[str]],
    imports_by_binding: BindingIndex,
    classes_by_location: BindingIndex,
    *,
    visited: frozenset[tuple[str, str]],
    enter_fields: bool,
    _aliases_seen: frozenset[tuple[str, str]] = frozenset(),
) -> _Position:
    decided = [
        (
            parameter,
            _Position()
            if parameter == "None"
            else _boundary_type_verdict(
                parameter,
                module,
                contract,
                exports_by_module,
                imports_by_binding,
                classes_by_location,
                enter_collections=True,
                visited=visited,
                enter_fields=enter_fields,
                _aliases_seen=_aliases_seen,
            ),
        )
        for parameter in parameters
    ]
    return _combine_position_verdicts(decided)


def _combine_position_verdicts(decided: list[tuple[str, _Position]]) -> _Position:
    reached = tuple(sorted({pair for _parameter, verdict in decided for pair in verdict.resolved}))
    violations = tuple(
        sorted(
            {
                violation
                for parameter, verdict in decided
                if verdict.violation is not None
                for violation in (
                    verdict.violations
                    or (
                        (
                            f"holding {parameter} {verdict.violation}",
                            verdict.path,
                            verdict.nested_annotation or parameter,
                        ),
                    )
                )
            },
            key=lambda item: (item[0], item[1], item[2] or ""),
        )
    )
    if violations:
        reason, path, nested_annotation = violations[0]
        return _Position(
            violation=reason,
            resolved=reached,
            path=path,
            nested_annotation=nested_annotation,
            violations=violations,
        )
    for _parameter, verdict in decided:
        if verdict.undecidable is not None:
            return _Position(
                undecidable=verdict.undecidable,
                resolved=reached,
                path=verdict.path,
                nested_annotation=verdict.nested_annotation,
                violations=verdict.violations,
            )
    return _Position(resolved=reached)


def _declared_facade_positions(
    item: RawRecord,
    contract: ArchitectureContract,
    exports_by_module: dict[str, frozenset[str]],
    imports: Sequence[RawRecord] = (),
    uncertain_reexport_origins: UncertainReexportOrigins | None = None,
) -> DeclaredFacade | None:
    """The (module, qualified name, annotated positions) of one declared facade function, or
    None when the record is not a module-level function its own `component.public` covers -- a
    naming convention used to guess at that last one (AD-63). No rule is consulted: whether a
    function is part of a component's declared facade is a fact about the contract and the
    scan, which `boundary_types` narrows to its own `source` and AD-65 reads unnarrowed.
    """
    data = item["data"]
    if item["kind"] != "function" or data.get("symbol_category") != "function":
        return None
    module, name = data["module"], data["name"]
    facade_entries: list[tuple[str, str, str, bool]] = []
    component = contract.component_for(module)
    if component is not None and _facade_covers(module, name, component, exports_by_module):
        facade_entries.append((module, name, module, False))

    origin = data["qualified_name"]
    reexport_entries = _reexport_facade_entries(
        origin,
        contract,
        exports_by_module,
        imports,
        uncertain_reexport_origins or {},
    )
    facade_entries.extend(reexport_entries)
    if not facade_entries:
        return None
    facade_entries = sorted(set(facade_entries))
    facade_module, facade_name, resolution_module, _ = facade_entries[0]
    # An unannotated position carries an empty annotation rather than being dropped: it is a
    # position of the facade the rule cannot decide, and dropping it hid it from the rule's own
    # denominator (AD-67).
    positions = [
        (parameter["name"], parameter["annotation"] or "") for parameter in data["parameters"]
    ]
    positions.append(("return", data["returns"] or ""))
    return (
        facade_module,
        f"{facade_module}.{facade_name}",
        positions,
        resolution_module,
        tuple(facade_entries),
    )


def _reexport_facade_entries(
    origin: str,
    contract: ArchitectureContract,
    exports_by_module: dict[str, frozenset[str]],
    imports: Sequence[RawRecord],
    uncertain_reexport_origins: UncertainReexportOrigins,
) -> list[FacadeEntry]:
    """Match re-export facts while keeping uncertain bindings scoped to one entry."""
    reexport_origins: dict[tuple[str, str], set[str]] = {}
    for imported in imports:
        imported_data = imported["data"]
        imported_origin = imported_data.get("origin_definition")
        if imported_data.get("reexport") and isinstance(imported_origin, str):
            binding_key = (imported_data["source_module"], imported_data["binding"])
            reexport_origins.setdefault(binding_key, set()).add(imported_origin)
    ambiguous_bindings = {
        binding for binding, origins in reexport_origins.items() if len(origins) > 1
    }
    facade_entries: list[FacadeEntry] = []
    for imported in imports:
        imported_data = imported["data"]
        binding_key = (imported_data.get("source_module"), imported_data.get("binding"))
        binding_name = f"{imported_data['source_module']}.{imported_data['binding']}"
        candidate_origins = uncertain_reexport_origins.get(binding_name, frozenset())
        own_uncertainty = origin in candidate_origins
        if not (imported_data.get("reexport") or own_uncertainty):
            continue
        chain = imported_data.get("reexport_chain", ())
        inherited_uncertainty = any(
            origin in uncertain_reexport_origins.get(alias, frozenset()) for alias in chain
        )
        entry_origin = imported_data.get("origin_definition")
        if entry_origin != origin and not own_uncertainty and not inherited_uncertainty:
            continue
        facade_module = imported_data["source_module"]
        binding = imported_data["binding"]
        resolution_module, _, _ = origin.rpartition(".")
        entry_uncertain = (
            own_uncertainty or binding_key in ambiguous_bindings or inherited_uncertainty
        )
        for owner in contract.components:
            if contract.component_for(facade_module) == owner and _facade_covers(
                facade_module, binding, owner, exports_by_module
            ):
                facade_entries.append((facade_module, binding, resolution_module, entry_uncertain))
    return facade_entries


def _facade_positions(
    item: RawRecord,
    rule: BoundaryTypesRule,
    contract: ArchitectureContract,
    exports_by_module: dict[str, frozenset[str]],
    imports: Sequence[RawRecord] = (),
    uncertain_reexport_origins: UncertainReexportOrigins | None = None,
) -> (
    tuple[
        str,
        str,
        list[tuple[str, str]],
        str,
        bool,
        tuple[tuple[str, str, str, bool], ...],
    ]
    | None
):
    """The declared facade positions `rule` must check, or None when the function is out of
    scope or exempted (AD-49)."""
    found = _declared_facade_positions(
        item, contract, exports_by_module, imports, uncertain_reexport_origins
    )
    if found is None:
        return None
    candidates = [
        entry
        for entry in found[4]
        if in_scope(entry[0], rule.source)
        and not any(in_scope(entry[0], allowed) for allowed in rule.allowed_sources)
        and entry[0] not in rule.exact_sources
    ]
    if not candidates:
        return None
    facade_module, facade_name, resolution_module, entry_uncertain = sorted(
        candidates, key=lambda entry: (entry[3], entry[:3])
    )[0]
    return (
        facade_module,
        f"{facade_module}.{facade_name}",
        found[2],
        resolution_module,
        entry_uncertain,
        found[4],
    )


def facade_signature_types(
    symbols: Sequence[RawRecord],
    imports: Sequence[RawRecord],
    contract: ArchitectureContract,
    exports_by_module: dict[str, frozenset[str]],
    uncertain_reexport_origins: UncertainReexportOrigins | None = None,
) -> list[RawRecord]:
    """Record on every declared facade function the types its signature exposes (AD-65).

    A type a facade signature names reaches the component's boundary whether or not another
    component imports it, so `interface_boundary`'s unused-entry check needs the same answer
    `boundary_types` already computes: `_declared_facade_positions` for which functions are
    facade, `_boundary_type_verdict`'s own `resolved` field (AD-69) for what an annotation
    resolves to. That one resolution is published here, as a `facade_types` key on the
    function's own symbol record beside the annotations it resolves, so `check.validation`
    reads the answer off the observation instead of deriving a second one that could disagree
    (AD-2's open payload, AD-4's one channel out of the analyzer).

    The key carries dotted `module.Name` origins, the shape an import's `reexport_chain`
    already uses, and is written only when at least one position resolves: an unresolved
    annotation reaches nothing, so recording an empty list would claim the function was
    inspected without saying anything a reader may act on. No `boundary_types` rule needs to
    be declared for this -- every component that declares a facade gets the same record,
    because `resolved` fills in on its own walk regardless of the verdict built alongside it.
    """
    imports_by_binding, classes_by_location = boundary_type_indexes(
        symbols,
        imports,
        contract,
        exports_by_module,
        uncertain_reexport_origins or {},
    )
    recorded: list[RawRecord] = []
    for item in symbols:
        found = _declared_facade_positions(
            item, contract, exports_by_module, imports, uncertain_reexport_origins
        )
        has_proven_facade = found is not None and any(not entry[3] for entry in found[4])
        names = (
            _resolved_position_types(
                found[3],
                found[2],
                contract,
                exports_by_module,
                imports_by_binding,
                classes_by_location,
            )
            if has_proven_facade and found is not None
            else []
        )
        recorded.append(
            {**item, "data": {**item["data"], "facade_types": names}} if names else item
        )
    return recorded


def _resolved_position_types(
    module: str,
    positions: Sequence[tuple[str, str]],
    contract: ArchitectureContract,
    exports_by_module: dict[str, frozenset[str]],
    imports_by_binding: BindingIndex,
    classes_by_location: BindingIndex,
) -> list[str]:
    """The distinct types one function's annotated positions resolve to, dotted and sorted.

    Reads `resolved` off `_boundary_type_verdict`'s own walk of each annotation (AD-69) instead
    of building a second candidate list: both readers take the bare name, and both take the
    element of a known collection, because a type inside a `list[...]` crosses the boundary
    exactly as the bare one does. A second, hand-kept reading would let `boundary_types` judge
    `list[Payload]` while `interface_boundary` called the very entry it judged unused -- the
    drift AD-65 exists to remove, reappearing wherever a future annotation shape is taught to
    only one of the two.
    """
    names = {
        f"{origin_module}.{origin_name}"
        for _, annotation in positions
        for origin_module, origin_name in _boundary_type_verdict(
            annotation,
            module,
            contract,
            exports_by_module,
            imports_by_binding,
            classes_by_location,
        ).resolved
    }
    return sorted(names)


def _boundary_type_allowance_fact(
    rule: BoundaryTypesRule, facade_module: str, record: RawRecord
) -> RawRecord | None:
    data = record["data"]
    path = data["path"] if "path" in data else None
    nested_annotation = data["nested_annotation"] if "nested_annotation" in data else None
    for allowance in rule.allowed_positions:
        if (
            allowance.annotation == "dict"
            or data["qualified_name"] != allowance.qualified_name
            or data["position"] != allowance.position
            or path != f"{allowance.position}.{allowance.field_path}"
            or nested_annotation != allowance.annotation
        ):
            continue
        return classified(
            item_id=stable_id(
                "TYPE",
                rule.id,
                record["id"],
                allowance.qualified_name,
                allowance.position,
                allowance.field_path,
                allowance.annotation,
            ),
            evidence_class=EvidenceClass.FACT,
            area="type_architecture",
            kind="boundary_type_allowance",
            title=(f"{allowance.qualified_name} has an exact nested boundary type allowance"),
            subjects=[allowance.qualified_name, facade_module],
            evidence_ids=record["evidence_ids"],
            rule_ids=[rule.id],
            fact_ids=record["fact_ids"],
            data={
                "qualified_name": allowance.qualified_name,
                "position": allowance.position,
                "field_path": allowance.field_path,
                "annotation": allowance.annotation,
            },
        )
    return None


def _boundary_types_violations(
    symbols: Sequence[RawRecord],
    imports: Sequence[RawRecord],
    contract: ArchitectureContract,
    exports_by_module: dict[str, frozenset[str]],
    uncertain_reexport_origins: UncertainReexportOrigins,
    source_modules: frozenset[str] | None = None,
) -> tuple[list[RawRecord], list[RawRecord]]:
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
        return [], []
    imports_by_binding, classes_by_location = boundary_type_indexes(
        symbols, imports, contract, exports_by_module, uncertain_reexport_origins
    )
    violations: list[RawRecord] = []
    allowance_facts: list[RawRecord] = []
    for rule in rules:
        for item in symbols:
            found = _facade_positions(
                item, rule, contract, exports_by_module, imports, uncertain_reexport_origins
            )
            if found is None:
                continue
            facade_module, qualname, positions, resolution_module, ambiguous_facade, _ = found
            if source_modules is not None and facade_module not in source_modules:
                continue
            for position, annotation in positions:
                verdict = (
                    _Position(undecidable="ambiguous_facade")
                    if ambiguous_facade
                    else _boundary_type_verdict(
                        annotation,
                        resolution_module,
                        contract,
                        exports_by_module,
                        imports_by_binding,
                        classes_by_location,
                    )
                )
                records = _boundary_type_violation_records(
                    rule,
                    item,
                    facade_module,
                    qualname,
                    position,
                    annotation,
                    verdict,
                )
                for record in records:
                    fact = _boundary_type_allowance_fact(rule, facade_module, record)
                    if fact is None:
                        violations.append(record)
                    else:
                        allowance_facts.append(fact)
    return sorted(violations, key=lambda item: item["id"]), sorted(
        allowance_facts, key=lambda item: item["id"]
    )


def _boundary_type_violation_records(
    rule: BoundaryTypesRule,
    item: RawRecord,
    facade_module: str,
    qualname: str,
    position: str,
    annotation: str,
    verdict: _Position,
) -> list[RawRecord]:
    if verdict.violation is None:
        return []
    verb = "returns" if position == "return" else f"takes {position} as"
    findings = sorted(
        set(verdict.violations or ((verdict.violation, verdict.path, verdict.nested_annotation),)),
        key=lambda finding: (finding[0], finding[1], finding[2] or ""),
    )
    records: list[RawRecord] = []
    for reason, path, nested_annotation in findings:
        path_data = ".".join((position, *path)) if path else None
        if path:
            identity_parts = (rule.id, item["id"], position, *path, nested_annotation or "", reason)
        elif len(findings) > 1:
            identity_parts = (rule.id, item["id"], position, nested_annotation or "", reason)
        else:
            identity_parts = (rule.id, item["id"], position)
        nested_fields = " ".join(f"field {name}" for name in path)
        field_detail = f"{nested_fields} " if nested_fields else ""
        records.append(
            classified(
                item_id=stable_id("VIO", *identity_parts),
                evidence_class=EvidenceClass.VIOLATION,
                area="type_architecture",
                kind=rule.kind,
                title=f"{qualname} {verb} {annotation} {field_detail}{reason}",
                subjects=[qualname, facade_module],
                evidence_ids=item["evidence_ids"],
                rule_ids=[rule.id],
                fact_ids=[item["id"]],
                data={
                    "source": rule.source,
                    "qualified_name": qualname,
                    "module": facade_module,
                    "position": position,
                    "annotation": annotation,
                    **({"path": path_data} if path_data else {}),
                    **(
                        {"nested_annotation": nested_annotation}
                        if path_data and nested_annotation
                        else {}
                    ),
                },
            )
        )
    return records


def _boundary_type_position_record(
    rule: BoundaryTypesRule,
    symbol: RawRecord,
    detail: RecordData,
) -> RawRecord:
    module = detail["module"]
    qualified_name = detail["qualified_name"]
    position = detail["position"]
    reason = detail["reason"]
    occurrence = detail["occurrence"]
    path = detail.get("path")
    location = f" at {path}" if isinstance(path, str) else ""
    return classified(
        item_id=stable_id(
            "UNKNOWN-BOUNDARY-TYPE-POSITION",
            rule.id,
            module,
            qualified_name,
            occurrence,
            position,
        ),
        evidence_class=EvidenceClass.UNKNOWN,
        area="type_architecture",
        kind="boundary_type_position",
        title=f"{qualified_name} {position}: {reason}{location}",
        subjects=[rule.source, module, qualified_name],
        evidence_ids=symbol["evidence_ids"],
        rule_ids=[rule.id],
        fact_ids=[symbol["id"]],
        data=detail,
    )


def _boundary_type_limit_record(
    rule: BoundaryTypesRule,
    seen: int,
    undecidable_positions: list[dict[str, object]],
) -> RawRecord | None:
    if not seen:
        # No positions means no declared facade function; `rule-without-subjects` already says so.
        return None
    decided = seen - len(undecidable_positions)
    if decided == seen:
        return None
    counts = dict.fromkeys(_UNDECIDABLE_KINDS, 0)
    for detail in undecidable_positions:
        reason = detail["reason"]
        if isinstance(reason, str):
            counts[reason] += 1
    return classified(
        item_id=stable_id("UNKNOWN-BOUNDARY-TYPES", rule.id),
        evidence_class=EvidenceClass.UNKNOWN,
        area="type_architecture",
        kind="boundary_type_limit",
        title=f"{rule.id} decided {decided} of {seen} declared facade type positions",
        subjects=[rule.source],
        rule_ids=[rule.id],
        data={
            "positions": seen,
            "decided": decided,
            "undecided": len(undecidable_positions),
            **counts,
            "undecidable_positions": undecidable_positions,
        },
    )


def _symbol_source_location(
    symbol: RawRecord, evidence: dict[str, RawEvidence]
) -> tuple[str, int, int]:
    item = evidence[symbol["evidence_ids"][0]]
    return item["file"], item["line"], item["column"]


def _uncertain_facade_position_records(
    item: RawRecord,
    rule: BoundaryTypesRule,
    facade_entries: Sequence[FacadeEntry],
    positions: Sequence[tuple[str, str]],
    selected: tuple[str, str, str],
    occurrences: dict[tuple[str, str], int],
) -> list[tuple[dict[str, object], RawRecord]]:
    records: list[tuple[dict[str, object], RawRecord]] = []
    for module, name, resolution_module, uncertain in facade_entries:
        if (
            not uncertain
            or (module, name, resolution_module) == selected
            or not in_scope(module, rule.source)
            or any(in_scope(module, allowed) for allowed in rule.allowed_sources)
            or module in rule.exact_sources
        ):
            continue
        qualname = f"{module}.{name}"
        key = (module, qualname)
        occurrence = occurrences.get(key, 0)
        occurrences[key] = occurrence + 1
        for position, annotation in positions:
            detail: dict[str, object] = {
                "module": module,
                "qualified_name": qualname,
                "position": position,
                "annotation": annotation,
                "reason": "ambiguous_facade",
                "occurrence": occurrence,
            }
            records.append((detail, _boundary_type_position_record(rule, item, detail)))
    return records


def _unresolved_public_alias_routes(
    rule: BoundaryTypesRule,
    symbols: Sequence[RawRecord],
    imports: Sequence[RawRecord],
    contract: ArchitectureContract,
    exports_by_module: dict[str, frozenset[str]],
    uncertain_reexport_origins: UncertainReexportOrigins,
    scanned_modules: set[str],
    stable_bindings_by_module: dict[str, frozenset[str]],
    source_modules: frozenset[str] | None = None,
) -> list[RawRecord]:
    records: dict[str, RawRecord] = {}
    symbols_by_binding: dict[tuple[str, str], list[RawRecord]] = defaultdict(list)
    imports_by_binding: dict[tuple[str, str], list[RawRecord]] = defaultdict(list)
    for item in symbols:
        data = item["data"]
        if "parent" not in data or data["parent"] is None:
            symbols_by_binding[(data["module"], data["name"])].append(item)
    for item in imports:
        data = item["data"]
        if data.get("module_level_import") is True:
            imports_by_binding[(data["source_module"], data["binding"])].append(item)
    for item in imports:
        data = item["data"]
        module, binding = data["source_module"], data["binding"]
        if (
            (source_modules is not None and module not in source_modules)
            or not data["symbol"]
            or not in_scope(module, rule.source)
            or any(in_scope(module, allowed) for allowed in rule.allowed_sources)
            or module in rule.exact_sources
        ):
            continue
        owner = contract.component_for(module)
        if owner is None or not _facade_covers(module, binding, owner, exports_by_module):
            continue
        route = (f"{module}.{binding}", *data.get("reexport_chain", ()))
        unresolved = tuple(
            alias
            for alias in route
            if alias in uncertain_reexport_origins and not uncertain_reexport_origins[alias]
        )
        if not unresolved and not _public_alias_route_has_unproven_hop(
            route,
            symbols_by_binding,
            imports_by_binding,
            scanned_modules,
            stable_bindings_by_module,
        ):
            continue
        qualified_name = f"{module}.{binding}"
        record = classified(
            item_id=stable_id("UNKNOWN-BOUNDARY-TYPE-ROUTE", rule.id, qualified_name),
            evidence_class=EvidenceClass.UNKNOWN,
            area="type_architecture",
            kind="boundary_type_route",
            title=f"{rule.id} cannot resolve a declared facade alias route",
            subjects=[qualified_name, module],
            evidence_ids=item["evidence_ids"],
            rule_ids=[rule.id],
            fact_ids=[item["id"]],
            data={
                "module": module,
                "qualified_name": qualified_name,
                "reason": "unresolved_reexport_route",
                "route": list(route),
            },
        )
        records[record["id"]] = record
    return sorted(records.values(), key=lambda item: item["id"])


def _public_alias_route_has_unproven_hop(
    route: tuple[str, ...],
    symbols_by_binding: dict[tuple[str, str], list[RawRecord]],
    imports_by_binding: dict[tuple[str, str], list[RawRecord]],
    scanned_modules: set[str],
    stable_bindings_by_module: dict[str, frozenset[str]],
) -> bool:
    """A public alias is known only while each traversed binding has one proven definition."""
    if not route:
        return True
    module, separator, binding = route[0].rpartition(".")
    if (
        not separator
        or module not in scanned_modules
        or binding not in stable_bindings_by_module.get(module, frozenset())
    ):
        return True
    for alias in route[1:]:
        alias_name: str = alias
        module, separator, name = alias_name.rpartition(".")
        if not separator:
            return True
        if module not in scanned_modules:
            return True
        definitions = symbols_by_binding.get((module, name), [])
        bindings = imports_by_binding.get((module, name), [])
        if definitions:
            if (
                len(definitions) != 1
                or bindings
                or name not in stable_bindings_by_module.get(module, frozenset())
            ):
                return True
            category = definitions[0]["kind"]
            return category not in {"function", "class", "static_constant"}
        if len(bindings) != 1:
            return True
        binding_data = bindings[0]["data"]
        if not binding_data["reexport"]:
            return True
    return False


def boundary_type_limits(
    symbols: Sequence[RawRecord],
    imports: Sequence[RawRecord],
    contract: ArchitectureContract,
    exports_by_module: dict[str, frozenset[str]],
    evidence: dict[str, RawEvidence],
    uncertain_reexport_origins: UncertainReexportOrigins,
    scanned_modules: set[str],
    stable_bindings_by_module: dict[str, frozenset[str]] | None = None,
    source_modules: frozenset[str] | None = None,
) -> list[RawRecord]:
    """Record undecidable facade positions as a non-gating UNKNOWN, preserving AD-67."""
    rules = [rule for rule in contract.rules if isinstance(rule, BoundaryTypesRule)]
    if not rules:
        return []
    imports_by_binding, classes_by_location = boundary_type_indexes(
        symbols,
        imports,
        contract,
        exports_by_module,
        uncertain_reexport_origins,
    )
    # The origin symbol can live outside the rule's source package when a facade re-exports it.
    # `_boundary_rule_positions` selects the declared facade, so origin-module filtering here
    # would drop an unannotated facade position before it can become UNKNOWN.
    ordered_symbols = sorted(symbols, key=lambda item: _symbol_source_location(item, evidence))
    limits: list[RawRecord] = []
    positions_out: list[RawRecord] = []
    for rule in rules:
        seen, undecidable_positions, rule_positions = _boundary_rule_positions(
            rule,
            ordered_symbols,
            contract,
            exports_by_module,
            imports,
            imports_by_binding,
            classes_by_location,
            uncertain_reexport_origins,
        )
        positions_out.extend(rule_positions)
        limit = _boundary_type_limit_record(rule, seen, undecidable_positions)
        if limit is not None:
            limits.append(limit)
        limits.extend(
            _unresolved_public_alias_routes(
                rule,
                symbols,
                imports,
                contract,
                exports_by_module,
                uncertain_reexport_origins,
                scanned_modules,
                stable_bindings_by_module or {},
                source_modules,
            )
        )
    return sorted([*positions_out, *limits], key=lambda item: item["id"])


def _boundary_rule_positions(
    rule: BoundaryTypesRule,
    ordered_symbols: Sequence[RawRecord],
    contract: ArchitectureContract,
    exports_by_module: dict[str, frozenset[str]],
    imports: Sequence[RawRecord],
    imports_by_binding: BindingIndex,
    classes_by_location: BindingIndex,
    uncertain_reexport_origins: UncertainReexportOrigins,
) -> tuple[int, list[dict[str, object]], list[RawRecord]]:
    undecidable_positions: list[dict[str, object]] = []
    positions_out: list[RawRecord] = []
    occurrences: dict[tuple[str, str], int] = {}
    seen = 0
    for item in ordered_symbols:
        found = _facade_positions(
            item, rule, contract, exports_by_module, imports, uncertain_reexport_origins
        )
        if found is None:
            continue
        module, qualified_name, positions, resolution_module, ambiguous_facade, _ = found
        callable_key = (module, qualified_name)
        occurrence = occurrences.get(callable_key, 0)
        occurrences[callable_key] = occurrence + 1
        details = _undecidable_declared_positions(
            module,
            qualified_name,
            positions,
            resolution_module,
            ambiguous_facade,
            contract,
            exports_by_module,
            imports_by_binding,
            classes_by_location,
            occurrence,
        )
        seen += len(positions)
        undecidable_positions.extend(details)
        positions_out.extend(
            _boundary_type_position_record(rule, item, detail) for detail in details
        )
        selected = _selected_facade(module, qualified_name, resolution_module)
        declared = _declared_facade_positions(
            item, contract, exports_by_module, imports, uncertain_reexport_origins
        )
        if declared is None:
            continue
        uncertain = _uncertain_facade_position_records(
            item, rule, declared[4], declared[2], selected, occurrences
        )
        for detail, record in uncertain:
            seen += 1
            undecidable_positions.append(detail)
            positions_out.append(record)
    return seen, undecidable_positions, positions_out


def _undecidable_declared_positions(
    module: str,
    qualified_name: str,
    positions: Sequence[tuple[str, str]],
    resolution_module: str,
    ambiguous_facade: bool,
    contract: ArchitectureContract,
    exports_by_module: dict[str, frozenset[str]],
    imports_by_binding: BindingIndex,
    classes_by_location: BindingIndex,
    occurrence: int,
) -> list[dict[str, object]]:
    details: list[dict[str, object]] = []
    for position, annotation in positions:
        verdict = (
            _Position(undecidable="ambiguous_facade")
            if ambiguous_facade
            else _boundary_type_verdict(
                annotation,
                resolution_module,
                contract,
                exports_by_module,
                imports_by_binding,
                classes_by_location,
            )
        )
        reason = verdict.undecidable
        if reason is None:
            continue
        detail: dict[str, object] = {
            "module": module,
            "qualified_name": qualified_name,
            "position": position,
            "annotation": annotation,
            "reason": reason,
            "occurrence": occurrence,
        }
        if verdict.path:
            detail["path"] = ".".join((position, *verdict.path))
            detail["nested_annotation"] = verdict.nested_annotation or annotation
        details.append(detail)
    return details


def _selected_facade(
    module: str, qualified_name: str, resolution_module: str
) -> tuple[str, str, str]:
    prefix = f"{module}."
    selected_name = qualified_name.removeprefix(prefix)
    return module, selected_name, resolution_module


def _public_api_symbol(
    symbols: Sequence[RawRecord],
    module: str,
    name: str,
    origins: tuple[tuple[str, str], ...],
    ambiguous: bool,
) -> RawRecord | None:
    """The one top-level symbol a `module:name` public_api entry resolves to, if any."""
    if ambiguous:
        return None
    locations = ((module, name), *origins) if len(origins) == 1 else ((module, name),)
    for location in locations:
        candidates = [
            item
            for item in symbols
            if item["data"].get("module") == location[0]
            and item["data"].get("name") == location[1]
            and item["data"].get("parent") is None
        ]
        if len(candidates) > 1:
            return None
        if candidates:
            return candidates[0]
    return None


def _public_api_annotations(symbol: RawRecord) -> list[str]:
    """AD-70's "externally visible signature": a declared function's parameter and return
    annotations, or a declared class's own public attribute annotations (`fields`, added to
    `symbols` for exactly this).
    """
    data = symbol["data"]
    if symbol["kind"] == "class":
        return [field["annotation"] for field in data["fields"] if field["annotation"]]
    annotations = [
        parameter["annotation"] for parameter in data["parameters"] if parameter["annotation"]
    ]
    if data["returns"]:
        annotations.append(data["returns"])
    return annotations


def public_api_exposed_types(
    public_api: Sequence[str],
    symbols: Sequence[RawRecord],
    imports: Sequence[RawRecord],
    modules: Sequence[RawRecord],
    contract: ArchitectureContract,
) -> dict[str, list[str]]:
    """Every `declarations.public_api` entry mapped to the non-builtin types its own signature
    exposes and no declared entry already names, as `module:name` strings (AD-70) -- the
    package-external twin of `boundary_types`, reading `_boundary_type_verdict`'s own `resolved`
    field (AD-69) rather than a second, bare-name-only reading of the same annotations: a type
    inside `tuple[X, ...]` or `list[X]` must be as visible here as it is to `boundary_types`, or
    the two readings disagree on silence. `check.validation` compares this published answer
    against the declared `public_api` set and resolves nothing itself (AD-2's open payload,
    AD-4's one channel out of the analyzer).

    An identifier is always the type's *origin*, `resolved`'s own pair -- the one name that is
    true of it regardless of which module a consumer happens to reach it through. A declared
    entry may name that same origin directly (`shop.model.entities:Order`, where `Order` is
    defined) or name a facade that only re-exports it (`archkeel.api:ViolationRow`, defined in
    `archkeel.ir.baseline`); both are legitimate promises for the same type, so a declared
    entry's own name is resolved exactly the same way, through the one shared walk, to decide
    which origin *it* names -- `declared_origins` below -- and an exposed type already covered
    that way is left out rather than reported as a second, redundant promise.

    A type whose origin module this scan never saw -- a builtin, a stdlib or a third-party type
    -- is not part of the promise a *scanned* package can make about itself, so it is left out
    here rather than reported as missing; `scanned_modules` is exactly `check._scanned_modules`'
    own source, read here instead of derived a second time.
    """
    if not public_api:
        return {}
    exports = exports_by_module(modules)
    imports_by_binding, classes_by_location = boundary_type_indexes(
        symbols, imports, contract, exports
    )
    scanned_modules = frozenset(item["data"]["qualified_name"] for item in modules)
    declared_positions = {
        entry: _boundary_type_verdict(
            declared_name,
            declared_module,
            contract,
            exports,
            imports_by_binding,
            classes_by_location,
        )
        for entry in public_api
        for declared_module, _, declared_name in [entry.partition(":")]
    }
    declared_origins = {
        pair for position in declared_positions.values() for pair in position.resolved
    }
    types: dict[str, list[str]] = {}
    for entry in public_api:
        module, _, name = entry.partition(":")
        position = declared_positions[entry]
        ambiguous = position.undecidable == "ambiguous_binding" or _binding_is_ambiguous(
            (module, name), imports_by_binding, classes_by_location
        )
        symbol = _public_api_symbol(symbols, module, name, position.resolved, ambiguous)
        if symbol is None:
            continue
        symbol_module = symbol["data"]["module"]
        resolved: set[str] = set()
        for annotation in _public_api_annotations(symbol):
            verdict = _boundary_type_verdict(
                annotation,
                symbol_module,
                contract,
                exports,
                imports_by_binding,
                classes_by_location,
            )
            resolved.update(
                f"{origin_module}:{origin_name}"
                for origin_module, origin_name in verdict.resolved
                if origin_module in scanned_modules
                and (origin_module, origin_name) not in declared_origins
            )
        types[entry] = sorted(resolved)
    return types


def _requires_covers(source: ContractComponent, target_label: str, target_module: str) -> bool:
    """True when a `requires` entry names the target and, if it lists `through`, one of those
    prefixes names the imported module (AD-42)."""
    return any(
        entry.component == target_label
        and (not entry.through or any(in_scope(target_module, m) for m in entry.through))
        for entry in source.requires or ()
    )


def requires_violations(
    imports: Sequence[RawRecord],
    contract: ArchitectureContract,
    *,
    assessment_facts: list[RawRecord] | None = None,
    assessment_parent: str | None = None,
    source_modules: frozenset[str] | None = None,
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
        evaluated: list[RawRecord] = []
        for item in imports:
            data = item["data"]
            source = contract.component_for(data["source_module"])
            target = contract.component_for(data["target_module"])
            if (
                source is None
                or target is None
                or source == target
                or (source_modules is not None and data["source_module"] not in source_modules)
                or (data["under_type_checking"] and not rule.include_type_checking)
            ):
                continue
            evaluated.append(item)
            if _requires_covers(source, target.label, data["target_module"]):
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
        if assessment_facts is not None and evaluated:
            assessment_facts.append(
                classified(
                    item_id=stable_id("INSIDE-REQUIRES-EVALUATION", assessment_parent, rule.id),
                    evidence_class=EvidenceClass.FACT,
                    area="components",
                    kind="inside_rule_evaluation",
                    title=f"{rule.id} evaluated its scoped imports",
                    subjects=[
                        module
                        for item in evaluated
                        for module in (
                            item["data"]["source_module"],
                            item["data"]["target_module"],
                        )
                    ],
                    evidence_ids=[
                        evidence_id for item in evaluated for evidence_id in item["evidence_ids"]
                    ],
                    rule_ids=[rule.id],
                    fact_ids=[item["id"] for item in evaluated],
                    data={"parent_id": assessment_parent},
                )
            )
    return sorted(violations, key=lambda item: item["id"])


def rule_violations(
    *,
    imports: Sequence[RawRecord],
    typing_signals: Sequence[RawRecord],
    constructs: Sequence[RawRecord],
    packages: Sequence[RawRecord],
    modules: Sequence[RawRecord],
    symbols: Sequence[RawRecord],
    blank_modules: frozenset[str],
    module_cycles: Sequence[RawRecord],
    contract: ArchitectureContract,
    exports_by_module: dict[str, frozenset[str]],
    profile: Profile,
    uncertain_reexport_origins: UncertainReexportOrigins | None = None,
    source_modules: frozenset[str] | None = None,
    source_roots: tuple[str, ...] = (),
    assessment_facts: list[RawRecord] | None = None,
    assessment_parent: str | None = None,
    boundary_contract: ArchitectureContract | None = None,
) -> tuple[list[RawRecord], list[RawRecord]]:
    """Evaluate every declared contract rule and return the sorted violation records."""
    components = tuple((component.label, component.packages) for component in contract.components)
    module_facts = [
        item
        for item in modules
        if source_modules is None or item["data"]["qualified_name"] in source_modules
    ]
    package_facts = [
        item
        for item in packages
        if source_modules is None
        or any(in_scope(item["data"]["qualified_name"], root) for root in source_roots)
    ]
    forbidden_matches = list(
        _forbidden_dependency_matches(imports, contract.rules, components, source_modules)
    )
    forbidden_rejected_ids = frozenset(item["id"] for _, item in forbidden_matches)
    boundary_violations, allowance_facts = _boundary_types_violations(
        symbols,
        imports,
        boundary_contract or contract,
        exports_by_module,
        uncertain_reexport_origins or {},
        source_modules,
    )
    checked = assessment_facts if assessment_facts is not None else []
    return sorted(
        [
            *_dependency_violations(iter(forbidden_matches)),
            *_construct_violations([*typing_signals, *constructs], contract.rules, source_modules),
            *_external_dependency_violations(imports, contract.rules, source_modules),
            *_external_completeness_violations(
                imports, modules, contract.rules, profile.standard_library, source_modules
            ),
            *requires_violations(
                imports,
                contract,
                assessment_facts=checked if assessment_facts is not None else None,
                assessment_parent=assessment_parent,
                source_modules=source_modules,
            ),
            *_assignment_violations(module_facts, contract, blank_modules),
            *_root_layout_violations(package_facts, module_facts, contract.rules),
            *_module_placement_violations(module_facts, contract),
            *_component_cycle_violations(imports, contract),
            *_module_cycle_violations(module_cycles, imports, contract, source_modules),
            *_interface_violations(
                imports, contract, exports_by_module, forbidden_rejected_ids, source_modules
            ),
            *_sibling_violations(imports, contract.rules, source_modules),
            *_symbol_placement_violations(symbols, contract.rules, source_modules),
            *boundary_violations,
        ],
        key=lambda item: item["id"],
    ), allowance_facts
