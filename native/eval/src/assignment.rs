// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! `complete_assignment`: each module below `source` has exactly one owner.
//!
//! Reference engine: `check/evaluation/rules.py` `_assignment_violations` (the violations; a blank file is
//! exempt) and `_rule_evaluation_facts_for_rule` with `_modules_for_rule_source` (the receipt).

use archkeel_contract::SourceRule;
use archkeel_model::{in_scope, Model};

use crate::violation::Violation;

/// The violations of the rule. Its receipt is a part of the scope proof (`Scope::complete`).
pub(crate) fn check(id: &str, rule: &SourceRule, model: &Model) -> Vec<Violation> {
    let source = rule.source().as_text();
    let mut violations: Vec<Violation> = model
        .graph()
        .modules()
        .iter()
        .filter(|(module, row)| {
            !row.blank() && in_scope(row.name(), source) && model.owner(*module).is_none()
        })
        .map(|(module, row)| Violation::unassigned(id, source, module, row))
        .collect();
    violations.sort_by(|a, b| a.id().cmp(b.id()));
    violations
}
