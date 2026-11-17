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

/// The proven classes that violate the rule. An unread class never becomes a violation.
pub fn violations(model: &Model, rule: &SymbolPlacement) -> Result<Vec<Class>, Reason> {
    let classes = Graph::placement(model.graph()).ok_or(Reason::Unsupported(Unsupported::Rule(
        RuleKind::SymbolPlacement,
    )))?;
    let mut found = Vec::new();
    for class in classes {
        if model.selects(&class.module)
            && in_scope(&class.name, SymbolPlacement::source(rule).as_text())
            && !allowed(rule, &class.module)
        {
            for kind in rule.class_kinds() {
                if kind_matches(class.kind, *kind) {
                    found.push(class.clone());
                    break;
                }
            }
        }
    }
    Ok(found)
}
