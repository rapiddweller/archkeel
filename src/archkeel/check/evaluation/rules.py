# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Evaluate declared class-A contract rules against scanner records."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterator, Sequence
from collections.abc import Set as AbstractSet
from pathlib import PurePosixPath
from typing import Final, TypeAlias, assert_never
from typing import Literal as _Literal

from archkeel.ir.facts import ConstructCapability, ConstructSupport
from archkeel.ir.facts_codec import RawData as RecordData
from archkeel.ir.facts_codec import RawRecord, classified
from archkeel.ir.graph import strongly_connected_components
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
    LayerOrderRule,
    NoComponentCyclesRule,
    RootLayoutRule,
    SiblingIsolationRule,
    SymbolPlacementRule,
    component_owns_module,
    in_scope,
    interface_covers_import,
    module_in_ownership,
    package_owners,
    stable_id,
)
from archkeel.ir.model import requires_covers as _requires_covers
from archkeel.ir.profiles import DeclarationField, Profile
from archkeel.ir.type_shapes import TypeShapeIndex

from .boundary_types import _AMBIGUOUS as _AMBIGUOUS
from .boundary_types import _BROAD_BOUNDARY_REASON as _BROAD_BOUNDARY_REASON
from .boundary_types import _BROAD_BOUNDARY_TYPES as _BROAD_BOUNDARY_TYPES
from .boundary_types import _BUILTIN_NAMES as _BUILTIN_NAMES
from .boundary_types import _COLLECTION_CONTAINERS as _COLLECTION_CONTAINERS
from .boundary_types import _EXEMPT_CLASS_KINDS as _EXEMPT_CLASS_KINDS
from .boundary_types import _OPAQUE_NATIVE_REASONS as _OPAQUE_NATIVE_REASONS
from .boundary_types import _PROVEN_MAPPINGS as _PROVEN_MAPPINGS
from .boundary_types import _PROVEN_SCALAR_LEAVES as _PROVEN_SCALAR_LEAVES
from .boundary_types import _UNDECIDABLE_KINDS as _UNDECIDABLE_KINDS
from .boundary_types import BindingIndex as BindingIndex
from .boundary_types import _ambiguous_method_group as _ambiguous_method_group
from .boundary_types import _AmbiguousBinding as _AmbiguousBinding
from .boundary_types import _annotation_shape_verdict as _annotation_shape_verdict
from .boundary_types import _apply_property_methods as _apply_property_methods
from .boundary_types import _bare_type_verdict as _bare_type_verdict
from .boundary_types import _base_route_member_static as _base_route_member_static
from .boundary_types import _binding_index as _binding_index
from .boundary_types import _binding_is_ambiguous as _binding_is_ambiguous
from .boundary_types import _bound_method_positions as _bound_method_positions
from .boundary_types import _boundary_rule_positions as _boundary_rule_positions
from .boundary_types import _boundary_rule_results as _boundary_rule_results
from .boundary_types import _boundary_type_allowance_fact as _boundary_type_allowance_fact
from .boundary_types import (
    _boundary_type_allowance_fact_record as _boundary_type_allowance_fact_record,
)
from .boundary_types import _boundary_type_limit_record as _boundary_type_limit_record
from .boundary_types import _boundary_type_position_record as _boundary_type_position_record
from .boundary_types import _boundary_type_verdict as _boundary_type_verdict
from .boundary_types import _boundary_type_violation_records as _boundary_type_violation_records
from .boundary_types import _boundary_types_violations as _boundary_types_violations
from .boundary_types import _BoundMethod as _BoundMethod
from .boundary_types import _collection_parameters as _collection_parameters
from .boundary_types import _collection_verdict as _collection_verdict
from .boundary_types import _combine_position_verdicts as _combine_position_verdicts
from .boundary_types import _combined_annotation_verdict as _combined_annotation_verdict
from .boundary_types import (
    _contained_mapping_allowance_matches as _contained_mapping_allowance_matches,
)
from .boundary_types import _declared_chain_positions as _declared_chain_positions
from .boundary_types import (
    _declared_facade_inherited_positions as _declared_facade_inherited_positions,
)
from .boundary_types import _declared_facade_method_positions as _declared_facade_method_positions
from .boundary_types import _declared_facade_positions as _declared_facade_positions
from .boundary_types import _declared_field_verdict as _declared_field_verdict
from .boundary_types import _direct_generic_candidate_types as _direct_generic_candidate_types
from .boundary_types import _effective_method_surface as _effective_method_surface
from .boundary_types import _enum_member_verdict as _enum_member_verdict
from .boundary_types import _facade_positions as _facade_positions
from .boundary_types import _field_position_verdict as _field_position_verdict
from .boundary_types import _FieldPosition as _FieldPosition
from .boundary_types import _has_star_import as _has_star_import
from .boundary_types import _index_owner_facade_type_states as _index_owner_facade_type_states
from .boundary_types import _inherited_facade_types as _inherited_facade_types
from .boundary_types import _inherited_generic_candidate_types as _inherited_generic_candidate_types
from .boundary_types import _is_broad_boundary_type as _is_broad_boundary_type
from .boundary_types import _is_static_literal_constant as _is_static_literal_constant
from .boundary_types import _mapping_container_verdict as _mapping_container_verdict
from .boundary_types import _mapping_parameters as _mapping_parameters
from .boundary_types import _MappingOccurrence as _MappingOccurrence
from .boundary_types import _member_origin_static as _member_origin_static
from .boundary_types import _method_signature_positions as _method_signature_positions
from .boundary_types import _MethodSurface as _MethodSurface
from .boundary_types import _named_type_verdict as _named_type_verdict
from .boundary_types import _nested_field_allowance_matches as _nested_field_allowance_matches
from .boundary_types import (
    _opaque_mapping_value_allowance_matches as _opaque_mapping_value_allowance_matches,
)
from .boundary_types import _opaque_mapping_value_depth as _opaque_mapping_value_depth
from .boundary_types import _owned_type_verdict as _owned_type_verdict
from .boundary_types import _Position as _Position
from .boundary_types import _property_chains as _property_chains
from .boundary_types import _PropertyMethods as _PropertyMethods
from .boundary_types import _proven_type_head as _proven_type_head
from .boundary_types import (
    _public_alias_route_has_unproven_hop as _public_alias_route_has_unproven_hop,
)
from .boundary_types import _public_api_base as _public_api_base
from .boundary_types import _public_api_field_positions as _public_api_field_positions
from .boundary_types import _public_api_generic_bindings as _public_api_generic_bindings
from .boundary_types import _public_api_limit as _public_api_limit
from .boundary_types import _public_api_positions as _public_api_positions
from .boundary_types import _public_api_symbol as _public_api_symbol
from .boundary_types import _record_boundary_evaluation as _record_boundary_evaluation
from .boundary_types import _reexport_facade_entries as _reexport_facade_entries
from .boundary_types import _resolved_position_types as _resolved_position_types
from .boundary_types import _root_broad_count as _root_broad_count
from .boundary_types import _scoped_facade_signature_types as _scoped_facade_signature_types
from .boundary_types import _selected_facade as _selected_facade
from .boundary_types import _split_type_parameters as _split_type_parameters
from .boundary_types import _substituted_type_bindings as _substituted_type_bindings
from .boundary_types import _symbol_source_location as _symbol_source_location
from .boundary_types import _type_alias_verdict as _type_alias_verdict
from .boundary_types import _typing_module_binding as _typing_module_binding
from .boundary_types import _typing_wrapper_inner as _typing_wrapper_inner
from .boundary_types import _typing_wrapper_verdict as _typing_wrapper_verdict
from .boundary_types import _uncertain_facade_position_records as _uncertain_facade_position_records
from .boundary_types import _undecidable_declared_positions as _undecidable_declared_positions
from .boundary_types import _union_parameters as _union_parameters
from .boundary_types import _unresolvable_shape as _unresolvable_shape
from .boundary_types import _unresolved_named_verdict as _unresolved_named_verdict
from .boundary_types import _unresolved_public_alias_routes as _unresolved_public_alias_routes
from .boundary_types import boundary_type_indexes as boundary_type_indexes
from .boundary_types import boundary_type_limits as boundary_type_limits
from .boundary_types import facade_signature_types as facade_signature_types
from .boundary_types import public_api_exposed_types as public_api_exposed_types
from .boundary_types import resolve_named_type as resolve_named_type
from .rule_support import DeclaredFacade as DeclaredFacade
from .rule_support import FacadeEntry as FacadeEntry
from .rule_support import ReexportIndex as ReexportIndex
from .rule_support import UncertainReexportOrigins as UncertainReexportOrigins
from .rule_support import _forbidden_dependency_matches as _forbidden_dependency_matches
from .rule_support import _forbidden_dependency_verdicts as _forbidden_dependency_verdicts
from .rule_support import _reexport_index as _reexport_index
from .rule_support import _rule_evaluation_receipt as _rule_evaluation_receipt
from .rule_support import _Verdict as _Verdict
from .rule_support import exports_by_module as exports_by_module


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
    allowance_facts: list[RawRecord] | None = None,
) -> list[RawRecord]:
    violations: list[RawRecord] = []
    for rule in rules:
        if not isinstance(rule, ForbiddenConstructRule):
            continue
        for item in signals:
            data = item["data"]
            construct: ForbiddenConstructKind | None = _CONSTRUCT_SIGNALS.get(item["kind"])
            if "construct" in data:
                construct = ForbiddenConstructKind(data["construct"])
            owner = data["owner"]
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
            allowance = next(
                (
                    entry
                    for entry in rule.allowed_type_ignores
                    if construct is ForbiddenConstructKind.TYPE_IGNORE
                    and data.get("qualified_name") == entry.qualified_name
                    and data.get("line") == entry.line
                    and data.get("statement") == entry.statement
                    and data.get("tag") == entry.tag
                ),
                None,
            )
            if allowance is not None:
                if allowance_facts is not None:
                    allowance_facts.append(
                        classified(
                            item_id=stable_id("TYPE-IGNORE-ALLOWANCE", rule.id, item["id"]),
                            evidence_class=EvidenceClass.FACT,
                            area="type_architecture",
                            kind="type_ignore_allowance",
                            title=f"{allowance.qualified_name}:{allowance.line} has an exact "
                            "type-ignore allowance",
                            subjects=[allowance.qualified_name],
                            evidence_ids=item["evidence_ids"],
                            rule_ids=[rule.id],
                            fact_ids=[item["id"]],
                            provenance=list(rule.provenance),
                            data={
                                "qualified_name": allowance.qualified_name,
                                "line": allowance.line,
                                "statement": allowance.statement,
                                "tag": allowance.tag,
                            },
                        )
                    )
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
                or not (
                    data["external_package"] == rule.dependency
                    if "external_package" in data
                    else in_scope(data["target_module"], rule.dependency)
                )
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
            root = data.get("external_package", target.split(".")[0])
            if data.get("builtin_target") or root in internal_roots or root in standard_library:
                continue
            if any(
                (
                    root == declared.dependency
                    if "external_package" in data
                    else in_scope(target, declared.dependency)
                )
                for declared in declared
            ):
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
            # Assignment retains its legacy exemption for all AST-empty files.
            if (
                module in blank
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
    contract: ArchitectureContract, level: _Literal["module"] | None
) -> list[NoComponentCyclesRule]:
    return [
        rule
        for rule in contract.rules
        if isinstance(rule, NoComponentCyclesRule) and rule.level == level
    ]


def _component_cycle_violations(
    imports: Sequence[RawRecord],
    contract: ArchitectureContract,
    modules: Sequence[RawRecord],
    *,
    assessment_facts: list[RawRecord] | None = None,
    scope: str = "root",
    unsupported_rules: frozenset[str] = frozenset(),
    cycle_scope_complete: bool = False,
    cycle_graph_components: tuple[str, ...] = (),
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
    for rule in rules:
        selected = tuple(
            sorted(
                {
                    component.label
                    for module in modules
                    if (component := contract.component_for(module["data"]["qualified_name"]))
                    is not None
                    and (rule.components is None or component.label in rule.components)
                }
            )
        )
        if selected and assessment_facts is not None and rule.kind not in unsupported_rules:
            assessment_facts.append(
                _rule_evaluation_receipt(
                    rule,
                    scope,
                    modules,
                    subjects=selected,
                    data={
                        "cycle_scope_complete": cycle_scope_complete,
                        "cycle_scope_components": selected,
                        "cycle_graph_components": cycle_graph_components,
                    },
                )
            )
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
    *,
    modules: Sequence[RawRecord],
    assessment_facts: list[RawRecord] | None = None,
    assessment_scope: str = "root",
    unsupported_rules: frozenset[str] = frozenset(),
    cycle_namespace_complete: bool = False,
) -> list[RawRecord]:
    """Report measured module SCCs that touch the rule's scope (AD-98)."""
    violations: list[RawRecord] = []
    for rule in _cycle_rules(contract, "module"):
        scope = (
            None
            if rule.components is None
            else tuple(
                component for component in contract.components if component.label in rule.components
            )
        )
        selected = tuple(
            name
            for module in modules
            if (name := module["data"]["qualified_name"])
            and (source_modules is None or name in source_modules)
            and (
                scope is None or any(component_owns_module(component, name) for component in scope)
            )
        )
        if selected and assessment_facts is not None and rule.kind not in unsupported_rules:
            assessment_facts.append(
                _rule_evaluation_receipt(
                    rule,
                    assessment_scope,
                    modules,
                    subjects=selected,
                    data={"cycle_scope_complete": cycle_namespace_complete},
                )
            )
        for cycle in module_cycles:
            members: list[str] = cycle["data"]["members"]
            if source_modules is not None and not any(
                member in source_modules for member in members
            ):
                continue
            if scope is not None and not any(
                component_owns_module(component, member)
                for member in members
                for component in scope
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


def _interface_allows(
    data: RecordData, target: ContractComponent, exports_by_module: dict[str, frozenset[str]]
) -> bool:
    """Decide whether one cross-component import reaches the target's declared interface."""
    if target.public is None:
        return True
    return interface_covers_import(
        data["target_module"], data["symbol"], data["reexport_chain"], target, exports_by_module
    )


def _interface_verdict(
    data: RecordData,
    target: ContractComponent,
    exports_by_module: dict[str, frozenset[str]],
    exporting: frozenset[str],
) -> _Verdict:
    """Decide one cross-component import against the target's declared interface.

    A named import with an unproven re-export route stays undecided. One that names none
    (AD-97) is allowed when its module is public, and a violation only when nothing the target
    library offers can be public: no `module:name` entry and no `export` that could pass one on.
    """
    if data["symbols_known"]:
        if _interface_allows(data, target, exports_by_module):
            return "allowed"
        if "reexport_candidates" in data and data["symbol_visibility"] == "public_name":
            return "undecided"
        return "violation"
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
    *,
    dependency_symbols: bool = True,
) -> list[RawRecord]:
    violations: list[RawRecord] = []
    for rule, item, source, target, verdict in _interface_verdicts(
        imports, contract, exports_by_module, forbidden_rejected_ids, source_modules
    ):
        if not dependency_symbols and any(":" in entry for entry in target.public or ()):
            continue
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
                    "reason": "The import's used names or publication route are unproven.",
                },
            )
        )
    return records


def symbol_limits(
    imports: Sequence[RawRecord],
    contract: ArchitectureContract,
    exports_by_module: dict[str, frozenset[str]],
    source_modules: frozenset[str] | None = None,
) -> list[RawRecord]:
    """UNKNOWN records for imports with unproven names or publication routes."""
    components = tuple(
        (component.label, component.packages, component.exact_modules or ())
        for component in contract.components
    )
    forbidden = list(
        _forbidden_dependency_verdicts(imports, contract.rules, components, source_modules)
    )
    rejected = frozenset(item["id"] for _, item, verdict in forbidden if verdict == "violation")
    interface = [
        (rule, item, verdict)
        for rule, item, _, _, verdict in _interface_verdicts(
            imports, contract, exports_by_module, rejected, source_modules
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
    if isinstance(
        rule, NoComponentCyclesRule | InterfaceBoundaryRule | CompleteRequiresRule | LayerOrderRule
    ):
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
    *,
    type_shapes: TypeShapeIndex,
) -> frozenset[str]:
    """Modules carrying at least one function `rule` actually inspects (issue #56).

    `source` matching a scanned module used to be enough: every non-underscore, module-level
    function under it was a subject. AD-63 reads the declared facade instead, so a component
    whose `public` is `None`, or whose `public` never covers a function under `source`, gives
    the rule zero functions to check -- a scanned module is no longer the same thing as a
    decided subject for this one rule kind, and `rule_subject_failures` has to see that instead
    of reading an empty result as a clean pass.
    """
    reexports = _reexport_index(imports)
    property_chains = _property_chains(symbols)
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
                reexports,
                property_chains,
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
            type_shapes=type_shapes,
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
    type_shapes: TypeShapeIndex,
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
        if isinstance(rule, LayerOrderRule) and contract is not None:
            rule_failures.extend(_layer_metadata_failures(contract, rule))
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
                type_shapes=type_shapes,
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


def profile_failures(
    contract: ArchitectureContract,
    profile: Profile,
    constructs: tuple[ConstructCapability, ...],
) -> list[RawRecord]:
    """One coverage failure per contract item the scanning profile cannot decide (AD-97).

    A rule the profile never evaluates would otherwise read as a clean pass; a declaration or
    budget it cannot observe would read as empty. Both gate the run with exit 2 instead.
    """
    declarations = contract.declarations or ContractDeclarations()
    supported = {entry.name for entry in constructs if entry.status != ConstructSupport.UNSUPPORTED}
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
            (
                rule.id,
                [rule.id],
                "constructs "
                + ", ".join(kind for kind in rule.constructs if kind not in supported),
            )
            for rule in contract.rules
            if isinstance(rule, ForbiddenConstructRule)
            and any(kind not in supported for kind in rule.constructs)
        ),
        *(
            (rule.id, [rule.id], "symbol-level dependency selector")
            for rule in contract.rules
            if isinstance(rule, ForbiddenDependencyRule)
            and rule.target_symbol is not None
            and not profile.dependency_symbols
        ),
        *(
            (component.id, [], "symbol-level public interface")
            for component in contract.components
            if not profile.dependency_symbols
            and any(":" in entry for entry in component.public or ())
        ),
        *(
            (component.id, [], "symbol-level required interface")
            for component in contract.components
            if not profile.dependency_symbols
            and any(
                ":" in entry for required in component.requires or () for entry in required.through
            )
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


def construct_capability_limits(
    contract: ArchitectureContract,
    constructs: tuple[ConstructCapability, ...],
    scope: str,
) -> list[RawRecord]:
    partial = {entry.name for entry in constructs if entry.status == ConstructSupport.PARTIAL}
    return [
        classified(
            item_id=stable_id("UNKNOWN-CONSTRUCT-CAPABILITY", scope, rule.id),
            evidence_class=EvidenceClass.UNKNOWN,
            area="type_architecture",
            kind="construct_capability_limit",
            title=f"{rule.id}: construct absence is only partially observed",
            subjects=[rule.source],
            rule_ids=[rule.id],
            data={"undecided": len(undecided), "constructs": undecided, "scope": scope},
        )
        for rule in contract.rules
        if isinstance(rule, ForbiddenConstructRule)
        and (undecided := [kind.value for kind in rule.constructs if kind in partial])
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


def requires_violations(
    imports: Sequence[RawRecord],
    contract: ArchitectureContract,
    *,
    assessment_facts: list[RawRecord] | None = None,
    assessment_parent: str | None = None,
    source_modules: frozenset[str] | None = None,
    dependency_symbols: bool = True,
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
            if not dependency_symbols and any(
                entry.component == target.label and any(":" in name for name in entry.through)
                for entry in source.requires or ()
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


def _cycle_rule_violations(
    imports: Sequence[RawRecord],
    module_cycles: Sequence[RawRecord],
    contract: ArchitectureContract,
    source_modules: frozenset[str] | None,
    modules: Sequence[RawRecord],
    assessment_facts: list[RawRecord] | None,
    scope: str,
    unsupported_rules: frozenset[str],
    cycle_scope_complete: bool,
    cycle_graph_components: tuple[str, ...],
    cycle_namespace_complete: bool,
) -> list[RawRecord]:
    return [
        *_component_cycle_violations(
            imports,
            contract,
            modules,
            assessment_facts=assessment_facts,
            scope=scope,
            unsupported_rules=unsupported_rules,
            cycle_scope_complete=cycle_scope_complete,
            cycle_graph_components=cycle_graph_components,
        ),
        *_module_cycle_violations(
            module_cycles,
            imports,
            contract,
            source_modules,
            modules=modules,
            assessment_facts=assessment_facts,
            assessment_scope=scope,
            unsupported_rules=unsupported_rules,
            cycle_namespace_complete=cycle_namespace_complete,
        ),
    ]


def _layer_order_components(
    contract: ArchitectureContract, rule: LayerOrderRule
) -> tuple[ContractComponent, ...]:
    selected = set(rule.components) if rule.components is not None else None
    sources = tuple(
        component
        for component in contract.components
        if selected is None or component.label in selected
    )
    targets = {entry.component for component in sources for entry in component.requires or ()}
    source_ids = {component.id for component in sources}
    return tuple(
        component
        for component in contract.components
        if component.id in source_ids or component.label in targets
    )


def _layer_order_violations(contract: ArchitectureContract, scope: str) -> list[RawRecord]:
    violations: list[RawRecord] = []
    components = {component.label: component for component in contract.components}
    for rule in contract.rules:
        if not isinstance(rule, LayerOrderRule):
            continue
        order = {layer: index for index, layer in enumerate(rule.layers)}
        for source in contract.components:
            if rule.components is not None and source.label not in rule.components:
                continue
            if source.layer is None or source.layer not in order:
                continue
            seen: set[str] = set()
            for entry in source.requires or ():
                if entry.component in seen:
                    continue
                seen.add(entry.component)
                target = components[entry.component]
                if (
                    target.layer is None
                    or target.layer not in order
                    or order[source.layer] >= order[target.layer]
                ):
                    continue
                violations.append(
                    classified(
                        item_id=stable_id("VIO-LAYER", rule.id, source.id, target.id),
                        fact_ids=[stable_id("RULE-EVALUATION", scope, rule.id)],
                        evidence_class=EvidenceClass.VIOLATION,
                        area="components",
                        kind=rule.kind,
                        title=(
                            f"{source.label} ({source.layer}) requires outer "
                            f"{target.label} ({target.layer})"
                        ),
                        subjects=[source.label, target.label],
                        rule_ids=[rule.id],
                        provenance=list(source.provenance),
                        data={
                            "source_component": source.label,
                            "target_component": target.label,
                            "source_layer": source.layer,
                            "target_layer": target.layer,
                            "rationale": entry.rationale,
                        },
                    )
                )
    return violations


def _layer_metadata_failures(
    contract: ArchitectureContract, rule: LayerOrderRule
) -> list[RawRecord]:
    return [
        classified(
            item_id=stable_id("UNKNOWN-LAYER", rule.id, component.id),
            evidence_class=EvidenceClass.UNKNOWN,
            area="components",
            kind="layer_metadata_missing",
            title=f"{component.label} has no layer in {rule.id} order",
            subjects=[component.label],
            rule_ids=[rule.id],
            provenance=list(component.provenance),
            data={"reason": "The component layer is absent or outside the order."},
        )
        for component in _layer_order_components(contract, rule)
        if component.layer not in rule.layers
    ]


def _layer_order_evaluation_facts(
    contract: ArchitectureContract, rule: LayerOrderRule, scope: str
) -> list[RawRecord]:
    selected = _layer_order_components(contract, rule)
    if not selected:
        return []
    return [
        _rule_evaluation_receipt(
            rule,
            scope,
            (),
            subjects=[component.label for component in selected],
            data={
                "claim": "declared_requires",
                "layers": list(rule.layers),
                "assessment_complete": all(
                    component.layer in rule.layers for component in selected
                ),
            },
        )
    ]


def _collect_rule_violations(
    *,
    imports: Sequence[RawRecord],
    typing_signals: Sequence[RawRecord],
    constructs: Sequence[RawRecord],
    modules: Sequence[RawRecord],
    symbols: Sequence[RawRecord],
    blank_modules: frozenset[str],
    module_cycles: Sequence[RawRecord],
    contract: ArchitectureContract,
    exports_by_module: dict[str, frozenset[str]],
    profile: Profile,
    source_modules: frozenset[str] | None,
    module_facts: Sequence[RawRecord],
    package_facts: Sequence[RawRecord],
    forbidden_matches: Sequence[tuple[ForbiddenDependencyRule, RawRecord]],
    forbidden_rejected_ids: frozenset[str],
    boundary_violations: Sequence[RawRecord],
    allowance_facts: list[RawRecord],
    assessment_facts: list[RawRecord] | None,
    assessment_parent: str | None,
    receipt_scope_complete: bool,
    cycle_scope_complete: bool,
    cycle_graph_components: tuple[str, ...],
    cycle_namespace_complete: bool,
) -> list[RawRecord]:
    result = [
        *_dependency_violations(iter(forbidden_matches)),
        *_construct_violations(
            [*typing_signals, *constructs], contract.rules, source_modules, allowance_facts
        ),
        *_external_dependency_violations(imports, contract.rules, source_modules),
        *_external_completeness_violations(
            imports, modules, contract.rules, profile.standard_library, source_modules
        ),
        *requires_violations(
            imports,
            contract,
            assessment_facts=assessment_facts,
            assessment_parent=assessment_parent,
            source_modules=source_modules,
            dependency_symbols=profile.dependency_symbols,
        ),
        *_layer_order_violations(contract, assessment_parent or "root"),
        *_assignment_violations(module_facts, contract, blank_modules),
        *_root_layout_violations(package_facts, module_facts, contract.rules),
        *_module_placement_violations(module_facts, contract),
        *_cycle_rule_violations(
            imports,
            module_cycles,
            contract,
            source_modules,
            module_facts,
            assessment_facts,
            assessment_parent or "root",
            profile.unsupported_rules,
            cycle_scope_complete,
            cycle_graph_components,
            cycle_namespace_complete,
        ),
        *_interface_violations(
            imports,
            contract,
            exports_by_module,
            forbidden_rejected_ids,
            source_modules,
            dependency_symbols=profile.dependency_symbols,
        ),
        *_sibling_violations(imports, contract.rules, source_modules),
        *_symbol_placement_violations(symbols, contract.rules, source_modules),
        *boundary_violations,
    ]
    if assessment_facts is not None:
        assessment_facts.extend(
            rule_evaluation_facts(
                contract,
                profile=profile,
                scope=assessment_parent or "root",
                modules=modules,
                source_modules=source_modules,
                blank_modules=blank_modules,
                receipt_scope_complete=receipt_scope_complete,
            )
        )
    return sorted(result, key=lambda item: item["id"])


def rule_violations(
    *,
    type_shapes: TypeShapeIndex,
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
    source_exact_modules: tuple[str, ...] = (),
    assessment_facts: list[RawRecord] | None = None,
    assessment_parent: str | None = None,
    ancestor_contracts: Sequence[ArchitectureContract] = (),
    cycle_scan_roots: tuple[str, ...] = (),
    cycle_namespace: str | None = None,
) -> tuple[list[RawRecord], list[RawRecord]]:
    """Evaluate every declared contract rule and return the sorted violation records."""
    components = tuple(
        (component.label, component.packages, component.exact_modules or ())
        for component in contract.components
    )
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
    forbidden_matches, forbidden_rejected_ids, boundary_violations, allowance_facts = (
        _boundary_rule_results(
            imports,
            symbols,
            contract,
            components,
            exports_by_module,
            uncertain_reexport_origins or {},
            source_modules,
            ancestor_contracts,
            profile,
            assessment_facts,
            assessment_parent or "root",
            type_shapes=type_shapes,
        )
    )
    cycle_namespace_complete, cycle_graph_components = _cycle_scan_coverage(
        contract, modules, profile, cycle_scan_roots, cycle_namespace
    )
    result = _collect_rule_violations(
        imports=imports,
        typing_signals=typing_signals,
        constructs=constructs,
        modules=modules,
        symbols=symbols,
        blank_modules=blank_modules,
        module_cycles=module_cycles,
        contract=contract,
        exports_by_module=exports_by_module,
        profile=profile,
        source_modules=source_modules,
        module_facts=module_facts,
        package_facts=package_facts,
        forbidden_matches=forbidden_matches,
        forbidden_rejected_ids=forbidden_rejected_ids,
        boundary_violations=boundary_violations,
        allowance_facts=allowance_facts,
        assessment_facts=assessment_facts,
        assessment_parent=assessment_parent,
        receipt_scope_complete=(
            not (
                package_scopes := (
                    *source_roots,
                    *(
                        package
                        for component in contract.components
                        for package in component.packages
                    ),
                )
            )
            or _scan_covers_packages(package_scopes, modules, profile, cycle_scan_roots)
        )
        and _scan_covers_exact_modules(
            tuple(
                module
                for module in (
                    *source_exact_modules,
                    *(
                        exact_module
                        for component in contract.components
                        for exact_module in component.exact_modules or ()
                    ),
                )
            ),
            modules,
            cycle_scan_roots,
        ),
        cycle_scope_complete=(
            len(cycle_graph_components) == len(contract.components) and bool(contract.components)
        ),
        cycle_graph_components=cycle_graph_components,
        cycle_namespace_complete=cycle_namespace_complete,
    )
    return result, allowance_facts


def _cycle_scan_coverage(
    contract: ArchitectureContract,
    modules: Sequence[RawRecord],
    profile: Profile,
    roots: tuple[str, ...],
    namespace: str | None,
) -> tuple[bool, tuple[str, ...]]:
    """Prove cycle domains are recursively inside configured scan roots."""
    if not roots or namespace is None:
        return False, ()

    components = tuple(
        sorted(
            component.label
            for component in contract.components
            if _scan_covers_ownership(component, modules, profile, roots)
        )
    )
    if profile.project_import_closure:
        # The caller supplies roots only after the collector proves complete project closure.
        scan_roots = tuple(_relative_path(root) for root in roots)
        namespace_complete = bool(modules) and all(
            in_scope(item["data"]["qualified_name"], namespace)
            and any(_contains(root, _relative_path(item["data"]["file"])) for root in scan_roots)
            for item in modules
        )
    elif profile.source_suffix == ".py":
        namespace_complete = _scan_covers_packages((namespace,), modules, profile, roots)
    else:
        return False, ()
    return namespace_complete, components


def _package_paths(
    package: str, modules: Sequence[RawRecord], profile: Profile
) -> frozenset[PurePosixPath]:
    package_parts = tuple(package.split("."))
    paths: set[PurePosixPath] = set()
    for record in modules:
        name = record["data"].get("qualified_name")
        file = record["data"].get("file")
        if not isinstance(name, str) or not isinstance(file, str) or not in_scope(name, package):
            continue
        if profile.source_suffix != ".py":
            extra_modules = len(name.split(".")) - len(package_parts)
            path = _relative_path(file).parent
            extra_parent_steps = max(extra_modules - 1, 0)
            for _ in range(extra_parent_steps):
                path = path.parent
            paths.add(path)
            continue
        file_path = _relative_path(file)
        directories = file_path.parent.parts
        module_parts = (
            directories if file_path.name == "__init__.py" else (*directories, file_path.stem)
        )
        anchor = next(
            (start for start in range(len(module_parts)) if ".".join(module_parts[start:]) == name),
            None,
        )
        if anchor is None:
            return frozenset()
        package_path = next(
            (
                PurePosixPath(*directories[:end])
                for end in range(anchor + 1, len(directories) + 1)
                if in_scope(".".join(module_parts[anchor:end]), package)
                and in_scope(name, ".".join(module_parts[anchor:end]))
            ),
            None,
        )
        if package_path is not None:
            paths.add(package_path)
        elif name == package and file_path.name != "__init__.py":
            paths.add(file_path.parent)
        else:
            return frozenset()
    return frozenset(paths)


def _scan_covers_packages(
    packages: Sequence[str],
    modules: Sequence[RawRecord],
    profile: Profile,
    roots: tuple[str, ...],
) -> bool:
    """Prove every observed physical domain of each package lies under scan roots."""
    if not packages or not roots:
        return False
    scan_roots = tuple(_relative_path(root) for root in roots)
    return all(
        (paths := _package_paths(package, modules, profile))
        and all(any(_contains(root, path) for root in scan_roots) for path in paths)
        for package in packages
    )


def _scan_covers_ownership(
    component: ContractComponent,
    modules: Sequence[RawRecord],
    profile: Profile,
    roots: tuple[str, ...],
) -> bool:
    scan_roots = tuple(_relative_path(root) for root in roots)
    return (
        bool(scan_roots)
        and (
            not component.packages
            or _scan_covers_packages(component.packages, modules, profile, roots)
        )
        and _scan_covers_exact_modules(component.exact_modules or (), modules, roots)
    )


def _scan_covers_exact_modules(
    exact_modules: Sequence[str], modules: Sequence[RawRecord], roots: tuple[str, ...]
) -> bool:
    scan_roots = tuple(_relative_path(root) for root in roots)
    return bool(scan_roots) and all(
        any(
            module["data"]["qualified_name"] == name
            and any(_contains(root, _relative_path(module["data"]["file"])) for root in scan_roots)
            for module in modules
        )
        for name in exact_modules
    )


def _relative_path(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    return PurePosixPath(*(part for part in path.parts if part not in {".", ""}))


def _contains(root: PurePosixPath, path: PurePosixPath) -> bool:
    return not root.is_absolute() and path.is_relative_to(root)


def rule_evaluation_facts(
    contract: ArchitectureContract,
    *,
    profile: Profile,
    scope: str,
    modules: Sequence[RawRecord],
    source_modules: frozenset[str] | None,
    blank_modules: frozenset[str],
    receipt_scope_complete: bool,
) -> list[RawRecord]:
    """Record completed evaluations or ownership blockers for one observation scope.

    Only `rule_evaluation` records certify completion. Blocker facts explain missing receipts
    without turning an incomplete scope into PASS. Declaration-only and unsupported rules
    have no evaluation receipt.
    """
    observed = tuple(
        item
        for item in modules
        if source_modules is None or item["data"]["qualified_name"] in source_modules
    )
    facts: list[RawRecord] = []
    for rule in contract.rules:
        if rule.kind in profile.unsupported_rules or isinstance(
            rule, AllowedDependencyRule | BoundaryTypesRule | NoComponentCyclesRule
        ):
            continue
        if isinstance(rule, LayerOrderRule):
            facts.extend(_layer_order_evaluation_facts(contract, rule, scope))
            continue
        if isinstance(rule, ExternalDependencyScopeRule):
            # allowed_sources is an exception list, not the rule's observed scope.
            selected = observed
        elif isinstance(rule, CompleteRequiresRule | InterfaceBoundaryRule):
            selected = (
                observed
                if _inside_rule_scope_is_complete(
                    contract, observed, profile, blank_modules, receipt_scope_complete
                )
                else ()
            )
            if not selected and receipt_scope_complete:
                facts.extend(
                    _inside_ownership_blockers(
                        rule, scope, contract, observed, profile, blank_modules
                    )
                )
        elif isinstance(rule, ForbiddenDependencyRule):
            selected = _modules_for_rule_source(rule.source, observed, contract)
        elif isinstance(rule, SiblingIsolationRule):
            selected = tuple(
                item
                for item in observed
                if any(in_scope(item["data"]["qualified_name"], member) for member in rule.members)
            )
        elif isinstance(rule, RootLayoutRule):
            selected = tuple(
                item for item in observed if in_scope(item["data"]["qualified_name"], rule.root)
            )
        elif isinstance(
            rule,
            ForbiddenConstructRule
            | CompleteAssignmentRule
            | CompleteExternalScopeRule
            | SymbolPlacementRule,
        ):
            selected = _modules_for_rule_source(rule.source, observed, contract)
        else:
            assert_never(rule)
        if selected:
            facts.append(_rule_evaluation_receipt(rule, scope, selected))
    return facts


def _inside_ownership_blockers(
    rule: CompleteRequiresRule | InterfaceBoundaryRule,
    scope: str,
    contract: ArchitectureContract,
    observed: Sequence[RawRecord],
    profile: Profile,
    blank_modules: frozenset[str],
) -> list[RawRecord]:
    blockers: list[RawRecord] = []
    for item in sorted(observed, key=lambda item: item["data"]["qualified_name"]):
        module = item["data"]["qualified_name"]
        owners = sorted(
            component.label
            for component in contract.components
            if component_owns_module(component, module)
        )
        if len(owners) == 1 or (
            not owners and _empty_python_initializer(item, profile, blank_modules)
        ):
            continue
        file = item["data"]["file"]
        reason = (
            f"{module} ({file}) has no owner in scope {scope}. "
            f'Assign it to one existing component using exact_modules: ["{module}"].'
            if not owners
            else f"{module} ({file}) has overlapping owners in scope {scope}: {', '.join(owners)}. "
            "Remove overlapping claims so exactly one component owns it."
        )
        blockers.append(
            classified(
                item_id=stable_id("RULE-OWNERSHIP-BLOCKER", scope, rule.id, item["id"]),
                evidence_class=EvidenceClass.FACT,
                area="rules",
                kind="rule_ownership_blocker",
                title=reason,
                subjects=[module],
                rule_ids=[rule.id],
                fact_ids=[item["id"]],
                evidence_ids=item["evidence_ids"],
                data={
                    "scope": scope,
                    "module": module,
                    "file": file,
                    "owners": owners,
                    "owner_count": len(owners),
                    "reason": reason,
                },
            )
        )
    return blockers


def _empty_python_initializer(
    item: RawRecord, profile: Profile, blank_modules: frozenset[str]
) -> bool:
    return (
        profile.source_suffix == ".py"
        and PurePosixPath(item["data"]["file"]).name == "__init__.py"
        and item["data"]["qualified_name"] in blank_modules
    )


def _inside_rule_scope_is_complete(
    contract: ArchitectureContract,
    observed: Sequence[RawRecord],
    profile: Profile,
    blank_modules: frozenset[str],
    receipt_scope_complete: bool,
) -> bool:
    if not receipt_scope_complete or not observed:
        return False
    ownership = tuple(
        (
            item,
            sum(
                component_owns_module(component, item["data"]["qualified_name"])
                for component in contract.components
            ),
        )
        for item in observed
    )
    return any(owner_count == 1 for _, owner_count in ownership) and all(
        owner_count == 1
        or (owner_count == 0 and _empty_python_initializer(item, profile, blank_modules))
        for item, owner_count in ownership
    )


def _modules_for_rule_source(
    source: str, observed: Sequence[RawRecord], contract: ArchitectureContract
) -> tuple[RawRecord, ...]:
    ownership = tuple(
        (component.label, component.packages, component.exact_modules or ())
        for component in contract.components
    )
    owners = package_owners(tuple((label, packages) for label, packages, _ in ownership))
    component = owners.get(source)
    ownership_by_label = {label: (packages, exact) for label, packages, exact in ownership}
    packages, exact = ownership_by_label[component] if component is not None else ((source,), ())
    return tuple(
        item
        for item in observed
        if module_in_ownership(item["data"]["qualified_name"], packages, exact)
    )
