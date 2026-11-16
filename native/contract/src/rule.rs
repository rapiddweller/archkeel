// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! One rule of the contract: a closed enum of the 23 rule kinds.

use crate::model::{
    AllowedDependency, CompleteRequires, ExternalDependencyScope, ForbiddenDependency,
    InterfaceBoundary, LayerOrder, NoComponentCycles, RootLayout, RuleHead, RuleKind,
    SiblingIsolation, SourceRule,
};
use crate::model_constructs::ForbiddenConstruct;
use crate::model_rules::{
    BoundaryTypes, BoundedNumericOperand, CallOwner, CatalogArgument, CatalogUse,
    ForbiddenCallArgument, ForbiddenEffectUnderCondition, ProtocolDeclarations, SourceOwnership,
    SymbolPlacement,
};
use crate::unused_public::UnusedPublic;

/// Declare the rule enum, its kind, its head and its body from one list of (variant, value type)
/// pairs. The call passes the visibility of the body (the crate), so the definition names no
/// `crate` that the scan cannot place.
macro_rules! rules {
    ($inner:vis, $($(#[$vdoc:meta])* $variant:ident($value:ty)),* $(,)?) => {
        /// One rule. Each variant holds the fields of its kind.
        #[derive(Clone, Debug, PartialEq, Eq, ::serde::Serialize)]
        #[serde(untagged)]
        pub enum Rule {
            $($(#[$vdoc])* $variant($value)),*
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
    /// A rule on who may call a target.
    CallOwner(CallOwner),
    /// A rule on an argument that no call may pass.
    ForbiddenCallArgument(ForbiddenCallArgument),
    /// A rule on an argument that a catalog limits.
    CatalogArgument(CatalogArgument),
    /// A rule on the use of a catalog value.
    CatalogUse(CatalogUse),
    /// A rule on an effect that a condition forbids.
    ForbiddenEffectUnderCondition(ForbiddenEffectUnderCondition),
    /// A rule on an import that is forbidden.
    ForbiddenDependency(ForbiddenDependency),
    /// A rule on an import that is allowed.
    AllowedDependency(AllowedDependency),
    /// A rule on a written construct that is forbidden.
    ForbiddenConstruct(ForbiddenConstruct),
    /// A rule on who owns a source value.
    SourceOwnership(SourceOwnership),
    /// A rule on where an external dependency may be imported.
    ExternalDependencyScope(ExternalDependencyScope),
    /// A rule that each module has one owner.
    CompleteAssignment(SourceRule),
    /// A rule on the children of a root.
    RootLayout(RootLayout),
    /// A rule that each external import is declared.
    CompleteExternalScope(SourceRule),
    /// A rule that each import is a declared requirement.
    CompleteRequires(CompleteRequires),
    /// A rule on the order of layers.
    LayerOrder(LayerOrder),
    /// A rule that no cycle exists.
    NoComponentCycles(NoComponentCycles),
    /// A rule on what an interface exposes.
    InterfaceBoundary(InterfaceBoundary),
    /// A rule that siblings do not import each other.
    SiblingIsolation(SiblingIsolation),
    /// A rule on where a kind of class may live.
    SymbolPlacement(SymbolPlacement),
    /// A rule on the types at a boundary.
    BoundaryTypes(BoundaryTypes),
    /// A rule on a bounded numeric operand.
    BoundedNumericOperand(BoundedNumericOperand),
    /// A rule on the declarations of a protocol.
    ProtocolDeclarations(ProtocolDeclarations),
    /// A rule that each public name of a component has a user in another component.
    UnusedPublic(UnusedPublic),
);
