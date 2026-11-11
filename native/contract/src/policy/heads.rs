// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Write access to the head of a rule, so that the tree can give a rule of an inside contract
//! the ID of its scope. `rule.rs` gives read access only.

use crate::model::RuleHead;
use crate::rule::Rule;

macro_rules! head_mut {
    ($rule:expr, $($variant:ident),* $(,)?) => {
        match $rule {
            $(Rule::$variant(value) => &mut value.head),*
        }
    };
}

/// The head of a rule, to change.
pub(crate) fn head_mut(rule: &mut Rule) -> &mut RuleHead {
    head_mut!(
        rule,
        CallOwner,
        ForbiddenCallArgument,
        CatalogArgument,
        CatalogUse,
        ForbiddenEffectUnderCondition,
        ForbiddenDependency,
        AllowedDependency,
        ForbiddenConstruct,
        SourceOwnership,
        ExternalDependencyScope,
        CompleteAssignment,
        RootLayout,
        CompleteExternalScope,
        CompleteRequires,
        LayerOrder,
        NoComponentCycles,
        InterfaceBoundary,
        SiblingIsolation,
        SymbolPlacement,
        BoundaryTypes,
        BoundedNumericOperand,
        ProtocolDeclarations,
    )
}
