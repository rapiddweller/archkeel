// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The contract word of a rule kind, as the rule row writes it (AD-381). The match lists every
//! kind and has no wildcard, so a new kind does not compile here until it has its word.

#![deny(
    clippy::wildcard_enum_match_arm,
    clippy::match_wildcard_for_single_variants
)]

use archkeel_contract::RuleKind;

/// The word of `kind` in the contract grammar.
pub(crate) fn word(kind: RuleKind) -> &'static str {
    match kind {
        RuleKind::CallOwner => "call_owner",
        RuleKind::ForbiddenCallArgument => "forbidden_call_argument",
        RuleKind::CatalogArgument => "catalog_argument",
        RuleKind::CatalogUse => "catalog_use",
        RuleKind::ForbiddenEffectUnderCondition => "forbidden_effect_under_condition",
        RuleKind::ForbiddenDependency => "forbidden_dependency",
        RuleKind::AllowedDependency => "allowed_dependency",
        RuleKind::ForbiddenConstruct => "forbidden_construct",
        RuleKind::SourceOwnership => "source_ownership",
        RuleKind::ExternalDependencyScope => "external_dependency_scope",
        RuleKind::CompleteAssignment => "complete_assignment",
        RuleKind::RootLayout => "root_layout",
        RuleKind::CompleteExternalScope => "complete_external_scope",
        RuleKind::CompleteRequires => "complete_requires",
        RuleKind::LayerOrder => "layer_order",
        RuleKind::NoComponentCycles => "no_component_cycles",
        RuleKind::InterfaceBoundary => "interface_boundary",
        RuleKind::SiblingIsolation => "sibling_isolation",
        RuleKind::SymbolPlacement => "symbol_placement",
        RuleKind::BoundaryTypes => "boundary_types",
        RuleKind::BoundedNumericOperand => "bounded_numeric_operand",
        RuleKind::ProtocolDeclarations => "protocol_declarations",
    }
}
