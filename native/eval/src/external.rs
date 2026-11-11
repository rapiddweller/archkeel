// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! `external_dependency_scope` and `complete_external_scope`: the rules over the external
//! targets of the resolved imports (slice S2).
//!
//! Reference engine: `check/evaluation/rules.py` `_external_dependency_violations` and
//! `_external_completeness_violations` (the violations), and `_rule_evaluation_facts_for_rule`
//! (the receipt: every module for `external_dependency_scope`, the modules of `source` for
//! `complete_external_scope`). An import with an external package matches a dependency by the
//! package name; any other import matches it by the scope of its target module.

use std::collections::HashSet;

use archkeel_contract::{ExternalDependencyScope, Rule, SourceRule};
use archkeel_model::{in_scope, Import, Model, Resolved};

use crate::violation::Violation;

/// True when the import names `dependency`.
fn names(import: &Import, dependency: &str) -> bool {
    match import.resolved() {
        Resolved::External(package) => package == dependency,
        Resolved::Local | Resolved::Builtin => in_scope(import.target_module(), dependency),
    }
}

/// The violations of an `external_dependency_scope` rule, and whether it has a receipt.
pub(crate) fn dependency_scope(
    id: &str,
    rule: &ExternalDependencyScope,
    model: &Model,
) -> (Vec<Violation>, bool) {
    let dependency = rule.dependency().as_text();
    let allowed = |source: &str| {
        rule.allowed_sources()
            .iter()
            .any(|allowed| in_scope(source, allowed.as_text()))
            || rule
                .exact_sources()
                .iter()
                .any(|exact| exact.as_text() == source)
    };
    let mut violations: Vec<Violation> = model
        .imports()
        .iter()
        .filter(|import| names(import, dependency) && !allowed(import.source_module()))
        .map(|import| Violation::outside_scope(id, dependency, import))
        .collect();
    violations.sort_by(|a, b| a.id().cmp(b.id()));
    (violations, !model.modules().is_empty())
}

/// The violations of a `complete_external_scope` rule, and whether it has a receipt.
pub(crate) fn complete_scope(
    id: &str,
    rule: &SourceRule,
    rules: &[Rule],
    model: &Model,
) -> (Vec<Violation>, bool) {
    let source = rule.source().as_text();
    let declared: Vec<&str> = rules
        .iter()
        .filter_map(|rule| match rule {
            Rule::ExternalDependencyScope(rule) => Some(rule.dependency().as_text()),
            _ => None,
        })
        .collect();
    let internal: HashSet<&str> = model
        .modules()
        .iter()
        .map(|(_, module)| root_of(module.name()))
        .collect();
    let mut violations: Vec<Violation> = Vec::new();
    for import in model.imports() {
        if import.relative() || !in_scope(import.source_module(), source) {
            continue;
        }
        let root = match import.resolved() {
            Resolved::External(package) => package.as_str(),
            Resolved::Builtin => continue,
            Resolved::Local => root_of(import.target_module()),
        };
        if internal.contains(root) || model.settings().standard(root) {
            continue;
        }
        if declared.iter().any(|dependency| names(import, dependency)) {
            continue;
        }
        violations.push(Violation::undeclared(id, source, root, import));
    }
    violations.sort_by(|a, b| a.id().cmp(b.id()));
    (violations, !model.source_modules(source).is_empty())
}

/// The first segment of a dotted name.
fn root_of(name: &str) -> &str {
    name.split('.').next().unwrap_or(name)
}
