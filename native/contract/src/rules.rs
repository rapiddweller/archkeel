// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The rule kind, the version gates of the rule features and the parser of each kind.

use crate::construct::forbidden_construct;
use crate::dependency::{allowed_dependency, external_dependency_scope, forbidden_dependency};
use crate::error::{invalid, unsupported, Parsed, Unported};
use crate::json::{field, has, Json};
use crate::model::{Rule, RuleKind};
use crate::read::object;
use crate::structure::{
    complete_requires, interface_boundary, layer_order, no_component_cycles, root_layout,
    sibling_isolation, source_rule,
};
use crate::version::{supports, ContractVersion, Feature};
use crate::words::{spelling, value_of};

/// `_rule_kind`.
pub(crate) fn rule_kind(raw: &Json, label: &str) -> Parsed<RuleKind> {
    match field(object(raw, label)?, "kind") {
        Some(Json::Text(value)) => value_of(value),
        _ => None,
    }
    .ok_or_else(|| invalid(format!("{label}.kind is unsupported")))
}

/// A rule kind that needs a feature, and the message when the version lacks it.
const KIND_GATES: [(RuleKind, Feature, &str); 9] = [
    (
        RuleKind::BoundedNumericOperand,
        Feature::BoundedNumericOperand,
        "bounded_numeric_operand requires contract schema_version 3.8.0",
    ),
    (
        RuleKind::CallOwner,
        Feature::CallOwner,
        "call_owner requires contract schema_version 3.7.0",
    ),
    (
        RuleKind::ProtocolDeclarations,
        Feature::ProtocolDeclarations,
        "protocol_declarations requires contract schema_version 3.9.0",
    ),
    (
        RuleKind::ForbiddenCallArgument,
        Feature::ForbiddenCallArgument,
        "forbidden_call_argument requires contract schema_version 3.10.0",
    ),
    (
        RuleKind::CatalogArgument,
        Feature::Catalog,
        "catalog rules require contract schema_version 3.14.0",
    ),
    (
        RuleKind::CatalogUse,
        Feature::Catalog,
        "catalog rules require contract schema_version 3.14.0",
    ),
    (
        RuleKind::ForbiddenEffectUnderCondition,
        Feature::GuardedEffect,
        "forbidden_effect_under_condition requires contract schema_version 3.13.0",
    ),
    (
        RuleKind::LayerOrder,
        Feature::Layers,
        "layer_order requires contract schema_version 2.3.0",
    ),
    (
        RuleKind::SourceOwnership,
        Feature::SourceOwnership,
        "source_ownership requires contract schema_version 3.12.0",
    ),
];

/// A rule field that needs a feature, whatever the kind of the rule.
const FIELD_GATES: [(&str, Feature, &str); 5] = [
    (
        "selector",
        Feature::ConstructSelector,
        "construct selectors require contract schema_version 3.11.0",
    ),
    (
        "source_match",
        Feature::ModuleSelectors,
        "dependency module selectors require contract schema_version 3.4.0",
    ),
    (
        "target_match",
        Feature::ModuleSelectors,
        "dependency module selectors require contract schema_version 3.4.0",
    ),
    (
        "target_kind",
        Feature::ImportNamespaces,
        "import namespace targets require contract schema_version 3.5.0",
    ),
    (
        "module_object_grants",
        Feature::ModuleObjectGrants,
        "module_object_grants require contract schema_version 3.6.0",
    ),
];

/// The version gates that Python checks after the kinds and before it parses a rule.
pub(crate) fn check_rule_features(
    version: ContractVersion,
    rules: &[Json],
    kinds: &[RuleKind],
) -> Parsed<()> {
    for (kind, feature, message) in KIND_GATES {
        if !supports(version, feature) && kinds.contains(&kind) {
            return Err(invalid(message));
        }
    }
    for (key, feature, message) in FIELD_GATES {
        if supports(version, feature) {
            continue;
        }
        for (index, raw) in rules.iter().enumerate() {
            if has(object(raw, &format!("rules[{index}]"))?, key) {
                return Err(invalid(message));
            }
        }
    }
    Ok(())
}

/// The parser of one rule. A kind that only the Python profile decides is `Unsupported`.
pub(crate) fn parse_rule(raw: &Json, label: &str, kind: RuleKind) -> Parsed<Rule> {
    match kind {
        RuleKind::ForbiddenDependency => {
            forbidden_dependency(raw, label).map(Rule::ForbiddenDependency)
        }
        RuleKind::AllowedDependency => allowed_dependency(raw, label).map(Rule::AllowedDependency),
        RuleKind::ForbiddenConstruct => {
            forbidden_construct(raw, label).map(Rule::ForbiddenConstruct)
        }
        RuleKind::ExternalDependencyScope => {
            external_dependency_scope(raw, label).map(Rule::ExternalDependencyScope)
        }
        RuleKind::CompleteAssignment => source_rule(raw, label).map(Rule::CompleteAssignment),
        RuleKind::RootLayout => root_layout(raw, label).map(Rule::RootLayout),
        RuleKind::CompleteExternalScope => source_rule(raw, label).map(Rule::CompleteExternalScope),
        RuleKind::CompleteRequires => complete_requires(raw, label).map(Rule::CompleteRequires),
        RuleKind::LayerOrder => layer_order(raw, label).map(Rule::LayerOrder),
        RuleKind::NoComponentCycles => no_component_cycles(raw, label).map(Rule::NoComponentCycles),
        RuleKind::InterfaceBoundary => interface_boundary(raw, label).map(Rule::InterfaceBoundary),
        RuleKind::SiblingIsolation => sibling_isolation(raw, label).map(Rule::SiblingIsolation),
        other => Err(unsupported(
            Unported::Rule(other),
            format!(
                "{label}.kind {} is not parsed in Rust yet (slice 0c-2)",
                spelling(&other)
            ),
        )),
    }
}

/// The kind of a parsed rule.
pub fn kind_of(rule: &Rule) -> RuleKind {
    match rule {
        Rule::ForbiddenDependency(_) => RuleKind::ForbiddenDependency,
        Rule::AllowedDependency(_) => RuleKind::AllowedDependency,
        Rule::ForbiddenConstruct(_) => RuleKind::ForbiddenConstruct,
        Rule::ExternalDependencyScope(_) => RuleKind::ExternalDependencyScope,
        Rule::CompleteAssignment(_) => RuleKind::CompleteAssignment,
        Rule::RootLayout(_) => RuleKind::RootLayout,
        Rule::CompleteExternalScope(_) => RuleKind::CompleteExternalScope,
        Rule::CompleteRequires(_) => RuleKind::CompleteRequires,
        Rule::LayerOrder(_) => RuleKind::LayerOrder,
        Rule::NoComponentCycles(_) => RuleKind::NoComponentCycles,
        Rule::InterfaceBoundary(_) => RuleKind::InterfaceBoundary,
        Rule::SiblingIsolation(_) => RuleKind::SiblingIsolation,
    }
}

/// The fields that each rule holds.
pub fn head_of(rule: &Rule) -> &crate::model::RuleHead {
    match rule {
        Rule::ForbiddenDependency(rule) => &rule.head,
        Rule::AllowedDependency(rule) => &rule.head,
        Rule::ForbiddenConstruct(rule) => &rule.head,
        Rule::ExternalDependencyScope(rule) => &rule.head,
        Rule::CompleteAssignment(rule) | Rule::CompleteExternalScope(rule) => &rule.head,
        Rule::RootLayout(rule) => &rule.head,
        Rule::CompleteRequires(rule) => &rule.head,
        Rule::LayerOrder(rule) => &rule.head,
        Rule::NoComponentCycles(rule) => &rule.head,
        Rule::InterfaceBoundary(rule) => &rule.head,
        Rule::SiblingIsolation(rule) => &rule.head,
    }
}
