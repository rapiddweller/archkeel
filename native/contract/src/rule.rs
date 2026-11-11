// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! One rule of the contract: a closed enum of the 22 rule kinds.

use crate::model::{
    AllowedDependency, CompleteRequires, ExternalDependencyScope, ForbiddenConstruct,
    ForbiddenDependency, InterfaceBoundary, LayerOrder, NoComponentCycles, RootLayout, RuleHead,
    RuleKind, SiblingIsolation, SourceRule,
};
use crate::model_rules::{
    BoundaryTypes, BoundedNumericOperand, CallOwner, CatalogArgument, CatalogUse,
    ForbiddenCallArgument, ForbiddenEffectUnderCondition, ProtocolDeclarations, SourceOwnership,
    SymbolPlacement,
};

/// Declare the rule enum, its kind, its head and its body from one list of (variant, value type)
/// pairs. The call passes the visibility of the body (the crate), so the definition names no
/// `crate` that the scan cannot place.
macro_rules! rules {
    ($inner:vis, $($variant:ident($value:ty)),* $(,)?) => {
        /// One rule. Each variant holds the fields of its kind.
        #[derive(Clone, Debug, PartialEq, Eq, ::serde::Serialize)]
        #[serde(untagged)]
        pub enum Rule {
            $($variant($value)),*
        }

        /// The kind of a rule.
        pub fn kind_of(rule: &Rule) -> RuleKind {
            match rule {
                $(Rule::$variant(_) => RuleKind::$variant),*
            }
        }

        /// The fields of a rule without its kind, in the order of its type.
        $inner fn body_of(rule: &Rule) -> ::serde_json::Value {
            match rule {
                $(Rule::$variant(value) => ::serde_json::to_value(value).unwrap_or_default()),*
            }
        }

        /// The fields that each rule holds.
        pub fn head_of(rule: &Rule) -> &RuleHead {
            match rule {
                $(Rule::$variant(value) => &value.head),*
            }
        }
    };
}

rules!(
    pub(crate),
    CallOwner(CallOwner),
    ForbiddenCallArgument(ForbiddenCallArgument),
    CatalogArgument(CatalogArgument),
    CatalogUse(CatalogUse),
    ForbiddenEffectUnderCondition(ForbiddenEffectUnderCondition),
    ForbiddenDependency(ForbiddenDependency),
    AllowedDependency(AllowedDependency),
    ForbiddenConstruct(ForbiddenConstruct),
    SourceOwnership(SourceOwnership),
    ExternalDependencyScope(ExternalDependencyScope),
    CompleteAssignment(SourceRule),
    RootLayout(RootLayout),
    CompleteExternalScope(SourceRule),
    CompleteRequires(CompleteRequires),
    LayerOrder(LayerOrder),
    NoComponentCycles(NoComponentCycles),
    InterfaceBoundary(InterfaceBoundary),
    SiblingIsolation(SiblingIsolation),
    SymbolPlacement(SymbolPlacement),
    BoundaryTypes(BoundaryTypes),
    BoundedNumericOperand(BoundedNumericOperand),
    ProtocolDeclarations(ProtocolDeclarations),
);
