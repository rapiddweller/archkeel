// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The rule kind, the version gates of the rule features and the parser of each kind.

use crate::boundary::{boundary_types, protocol_declarations};
use crate::construct::forbidden_construct;
use crate::dependency::{allowed_dependency, external_dependency_scope, forbidden_dependency};
use crate::error::{invalid, Parsed};
use crate::json::{field, has, Json};
use crate::model::RuleKind;
use crate::python_rules::{
    bounded_numeric_operand, call_owner, catalog_argument, catalog_use, forbidden_call_argument,
    forbidden_effect_under_condition, source_ownership, symbol_placement,
};
use crate::read::object;
use crate::rule::Rule;
use crate::structure::{
    complete_requires, interface_boundary, layer_order, no_component_cycles, root_layout,
    sibling_isolation, source_rule,
};
use crate::version::{supports, ContractVersion, Feature};
use crate::words::value_of;

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

type Parser = fn(&Json, &str) -> Parsed<Rule>;

/// The parser of each kind (`_RULE_PARSERS`).
const PARSERS: [(RuleKind, Parser); 22] = [
    (RuleKind::ForbiddenDependency, |raw, label| {
        forbidden_dependency(raw, label).map(Rule::ForbiddenDependency)
    }),
    (RuleKind::AllowedDependency, |raw, label| {
        allowed_dependency(raw, label).map(Rule::AllowedDependency)
    }),
    (RuleKind::ForbiddenConstruct, |raw, label| {
        forbidden_construct(raw, label).map(Rule::ForbiddenConstruct)
    }),
    (RuleKind::ExternalDependencyScope, |raw, label| {
        external_dependency_scope(raw, label).map(Rule::ExternalDependencyScope)
    }),
    (RuleKind::CompleteAssignment, |raw, label| {
        source_rule(raw, label).map(Rule::CompleteAssignment)
    }),
    (RuleKind::RootLayout, |raw, label| {
        root_layout(raw, label).map(Rule::RootLayout)
    }),
    (RuleKind::CompleteExternalScope, |raw, label| {
        source_rule(raw, label).map(Rule::CompleteExternalScope)
    }),
    (RuleKind::CompleteRequires, |raw, label| {
        complete_requires(raw, label).map(Rule::CompleteRequires)
    }),
    (RuleKind::LayerOrder, |raw, label| {
        layer_order(raw, label).map(Rule::LayerOrder)
    }),
    (RuleKind::NoComponentCycles, |raw, label| {
        no_component_cycles(raw, label).map(Rule::NoComponentCycles)
    }),
    (RuleKind::InterfaceBoundary, |raw, label| {
        interface_boundary(raw, label).map(Rule::InterfaceBoundary)
    }),
    (RuleKind::SiblingIsolation, |raw, label| {
        sibling_isolation(raw, label).map(Rule::SiblingIsolation)
    }),
    (RuleKind::SymbolPlacement, |raw, label| {
        symbol_placement(raw, label).map(Rule::SymbolPlacement)
    }),
    (RuleKind::SourceOwnership, |raw, label| {
        source_ownership(raw, label).map(Rule::SourceOwnership)
    }),
    (RuleKind::BoundaryTypes, |raw, label| {
        boundary_types(raw, label).map(Rule::BoundaryTypes)
    }),
    (RuleKind::ProtocolDeclarations, |raw, label| {
        protocol_declarations(raw, label).map(Rule::ProtocolDeclarations)
    }),
    (RuleKind::CallOwner, |raw, label| {
        call_owner(raw, label).map(Rule::CallOwner)
    }),
    (RuleKind::BoundedNumericOperand, |raw, label| {
        bounded_numeric_operand(raw, label).map(Rule::BoundedNumericOperand)
    }),
    (RuleKind::ForbiddenCallArgument, |raw, label| {
        forbidden_call_argument(raw, label).map(Rule::ForbiddenCallArgument)
    }),
    (RuleKind::CatalogArgument, |raw, label| {
        catalog_argument(raw, label).map(Rule::CatalogArgument)
    }),
    (RuleKind::CatalogUse, |raw, label| {
        catalog_use(raw, label).map(Rule::CatalogUse)
    }),
    (RuleKind::ForbiddenEffectUnderCondition, |raw, label| {
        forbidden_effect_under_condition(raw, label).map(Rule::ForbiddenEffectUnderCondition)
    }),
];

/// The parser of one rule.
pub(crate) fn parse_rule(raw: &Json, label: &str, kind: RuleKind) -> Parsed<Rule> {
    let parser = PARSERS
        .iter()
        .find(|(known, _)| *known == kind)
        .map(|(_, parser)| *parser);
    parser.map_or_else(
        || Err(invalid(format!("{label}.kind is unsupported"))),
        |parse| parse(raw, label),
    )
}

/// The version gates of the allowed boundary positions, after Python parses every rule.
pub(crate) fn check_boundary_features(version: ContractVersion, rules: &[Rule]) -> Parsed<()> {
    let positions = rules.iter().flat_map(|rule| match rule {
        Rule::BoundaryTypes(rule) => rule.allowed_positions.as_slice(),
        _ => &[],
    });
    for position in positions {
        let gates = [
            (position.alias_body.is_some(), ContractVersion::V3_0, "alias_body requires contract schema_version 3.0.0"),
            (position.key_alias_body.is_some(), ContractVersion::V3_1, "key_alias_body requires contract schema_version 3.1.0"),
            (position.literal_mapping_arm.is_some(), ContractVersion::V3_2, "literal_mapping_arm requires contract schema_version 3.2.0"),
            (
                position.native_mapping
                    || (position.literal_mapping_arm.is_some() && position.container_depth.is_some()),
                ContractVersion::V3_3,
                "native_mapping and literal-arm object values require contract schema_version 3.3.0",
            ),
        ];
        if let Some((_, _, message)) = gates
            .iter()
            .find(|(used, first, _)| *used && version < *first)
        {
            return Err(invalid(*message));
        }
    }
    Ok(())
}
