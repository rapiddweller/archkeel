// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Written classes and the scope receipt for `symbol_placement` (AD-728).

use archkeel_contract::{RuleKind, SymbolClassKind, SymbolPlacement};
use archkeel_facts::vocab::ClassKind;

use crate::model::Model;
use crate::ownership::in_scope;
use crate::placement_facts::Class;
use crate::reason::{Reason, Unsupported};

fn allowed(rule: &SymbolPlacement, module: &str) -> bool {
    rule.allowed_sources()
        .iter()
        .any(|scope| in_scope(module, scope.as_text()))
        || rule
            .exact_sources()
            .iter()
            .any(|scope| module == scope.as_text())
}

fn kind_matches(kind: ClassKind, expected: SymbolClassKind) -> bool {
    matches!(
        (kind, expected),
        (ClassKind::Class, SymbolClassKind::Class)
            | (ClassKind::Dataclass, SymbolClassKind::Dataclass)
            | (ClassKind::Enum, SymbolClassKind::Enum)
            | (ClassKind::Protocol, SymbolClassKind::Protocol)
            | (ClassKind::PydanticModel, SymbolClassKind::PydanticModel)
    )
}

/// The proven classes that violate the rule. An unread class never becomes a violation.
pub fn violations(model: &Model, rule: &SymbolPlacement) -> Result<Vec<Class>, Reason> {
    let classes = model
        .graph()
        .placement()
        .ok_or(Reason::Unsupported(Unsupported::Rule(
            RuleKind::SymbolPlacement,
        )))?;
    Ok(classes
        .iter()
        .filter(|class| {
            model.selects(&class.module)
                && in_scope(&class.name, rule.source().as_text())
                && !allowed(rule, &class.module)
                && rule
                    .class_kinds()
                    .iter()
                    .any(|kind| kind_matches(class.kind, *kind))
        })
        .cloned()
        .collect())
}
