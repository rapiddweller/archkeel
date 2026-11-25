// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Written classes and the scope receipt for `symbol_placement` (AD-728).

use archkeel_contract::{RuleKind, SymbolClassKind, SymbolPlacement};
use archkeel_facts::vocab::ClassKind;

use crate::graph::Graph;
use crate::model::Model;
use crate::ownership::in_scope;
use crate::placement_facts::Class;
use crate::reason::{Reason, Unsupported};
use crate::selection::{unused_by_module, UnusedAllowance};

fn allowed(rule: &SymbolPlacement, module: &str) -> bool {
    for scope in rule.allowed_sources() {
        if in_scope(module, scope.as_text()) {
            return true;
        }
    }
    for scope in rule.exact_sources() {
        if module == scope.as_text() {
            return true;
        }
    }
    false
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

/// The classes of a kind that the rule names, before its `allowed_sources` apply.
fn named_classes(model: &Model, rule: &SymbolPlacement) -> Result<Vec<Class>, Reason> {
    let classes = Graph::placement(model.graph()).ok_or(Reason::Unsupported(Unsupported::Rule(
        RuleKind::SymbolPlacement,
    )))?;
    let mut found = Vec::new();
    for class in classes {
        if !model.selects(&class.module)
            || !in_scope(&class.name, SymbolPlacement::source(rule).as_text())
        {
            continue;
        }
        for kind in rule.class_kinds() {
            if kind_matches(class.kind, *kind) {
                Vec::push(&mut found, class.clone());
                break;
            }
        }
    }
    Ok(found)
}

/// The proven classes that violate the rule. An unread class never becomes a violation.
pub fn violations(model: &Model, rule: &SymbolPlacement) -> Result<Vec<Class>, Reason> {
    let mut found = named_classes(model, rule)?;
    found.retain(|class| !allowed(rule, &class.module));
    Ok(found)
}

/// The exception entries of a rule that name no class of its kinds (AD-1070). A rule that reads no
/// class reports none: the collector can leave a class of an unproven kind unread.
pub(crate) fn unused_allowances(model: &Model, rule: &SymbolPlacement) -> Vec<UnusedAllowance> {
    let classes = named_classes(model, rule).unwrap_or_default();
    let modules: Vec<&str> = classes.iter().map(|class| class.module.as_str()).collect();
    if modules.is_empty() {
        return Vec::new();
    }
    unused_by_module(
        rule.allowed_sources(),
        rule.exact_sources(),
        &modules,
        |_| false,
    )
}
