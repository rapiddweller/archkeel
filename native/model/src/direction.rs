// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The import matchers of the direction rule kinds (slice S5, AD-380).
//!
//! Each matcher judges the resolved imports of the reply for one rule. The evaluator writes a
//! violation for each `Judged::Fail`; the scope proof counts each `Judged::Undecided` as an
//! undecided position. One matcher serves both, as `_forbidden_dependency_verdicts` and
//! `_requires_import_verdicts` serve the violations and `symbol_limits` in the reference engine.
//!
//! Reference engine: `check/evaluation/rule_support.py:98` `_forbidden_dependency_verdicts`,
//! `ir/dependency.py:111` `DependencySelector.select`, `check/evaluation/rules.py:1387`
//! `_sibling_violations`, `rules.py:1827` `_requires_import_verdicts` and `ir/model.py:318`
//! `requires_covers`, `:340` `_required_port_assessment`, `:356` `requires_import_assessment`.

use std::collections::HashMap;

use archkeel_contract::{CompleteRequires, Component, ForbiddenDependency, SiblingIsolation};

use crate::{
    ids::ComponentId, imports::Import, model::Model, ownership::in_scope, ownership::owner_of,
    selection::dependency_sides,
};

/// The judgement of one import that a rule names.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Judged {
    /// The rule rejects the import.
    Fail,
    /// The rule accepts the import.
    Pass,
    /// The reply does not prove which names the import uses: an undecided position.
    Undecided,
}

/// The judgement of each import that a `forbidden_dependency` rule names, in reply order. A mount
/// judges only the imports whose source lies in its domain (AD-385).
pub fn forbidden<'m>(model: &'m Model, rule: &'m ForbiddenDependency) -> Vec<(&'m Import, Judged)> {
    let [sources, targets] = dependency_sides(rule, model.contract().components());
    let allowed = |module: &str| rule.allowed_sources().iter().any(|a| a.as_text() == module);
    model
        .graph()
        .imports()
        .iter()
        .filter(|import| {
            model.selects(import.source_module())
                && sources.matches(import.source_module())
                && targets.matches(import.target_module())
                && !allowed(import.source_module())
                && !(import.under_type_checking() && !rule.include_type_checking())
        })
        .map(|import| {
            // AD-434: named type publication does not lift dependency symbol limits.
            let judged = match rule.target_symbol() {
                None => Judged::Fail,
                Some(symbol) if import.symbol() == Some(symbol.as_str()) => Judged::Fail,
                Some(_)
                    if import.symbols_known()
                        && (!import.under_type_checking() || import.symbol().is_none()) =>
                {
                    Judged::Pass
                }
                Some(_) => Judged::Undecided,
            };
            (import, judged)
        })
        .collect()
}

/// Each import from one member of a `sibling_isolation` rule to another member, with the member
/// of its source. The rule rejects each of them.
pub fn peers<'m>(model: &'m Model, rule: &'m SiblingIsolation) -> Vec<(&'m Import, &'m str)> {
    let member = |module: &str| {
        rule.members()
            .iter()
            .map(|m| m.as_text())
            .find(|m| in_scope(module, m))
    };
    model
        .graph()
        .imports()
        .iter()
        .filter(|import| model.selects(import.source_module()))
        .filter_map(|import| {
            let source = member(import.source_module())?;
            let target = member(import.target_module())?;
            let hidden = import.under_type_checking() && !rule.include_type_checking();
            (source != target && !hidden).then_some((import, source))
        })
        .collect()
}

/// One import between two components that a `complete_requires` rule judges.
#[derive(Clone, Copy, Debug)]
pub struct Crossing<'m> {
    pub import: &'m Import,
    pub source: &'m Component,
    pub target: &'m Component,
    pub judged: Judged,
}

/// The judgement of each import between two owned components, in reply order.
///
/// Without the symbol feature a profile does not judge an import whose target has a `through`
/// entry with a symbol (`dependency_symbols` is false): the import is left out, and the profile
/// limit of the scope proof (`limits.rs`) names such an entry. Without a statement of the
/// collector it holds the whole run; with a stated `Unsupported` it holds each `complete_requires`
/// rule (AD-482).
pub fn crossings<'m>(model: &'m Model, rule: &CompleteRequires) -> Vec<Crossing<'m>> {
    let components = model.components();
    // `dependency_symbols`: a profile judges symbol ports only with the symbol feature
    // (`check/evaluation/evaluate.py:1061`).
    let symbols = model.graph().observed().symbol_feature;
    let mut owners: HashMap<&str, Option<ComponentId>> = HashMap::new();
    let mut owner = |module: &'m str| {
        *owners
            .entry(module)
            .or_insert_with(|| owner_of(components, module))
    };
    let mut found = Vec::new();
    // A mount judges only the imports of its domain (`source_modules`, AD-385).
    let imports = model.graph().imports().iter();
    for import in imports.filter(|import| model.selects(import.source_module())) {
        let (Some(from), Some(to)) = (owner(import.source_module()), owner(import.target_module()))
        else {
            continue;
        };
        if from == to || (import.under_type_checking() && !rule.include_type_checking()) {
            continue;
        }
        let (Some(source), Some(target)) = (components.get(from), components.get(to)) else {
            continue;
        };
        if !symbols && symbol_port(source, target) {
            continue;
        }
        let judged = assessment(source, target, import);
        found.push(Crossing {
            import,
            source,
            target,
            judged,
        });
    }
    found
}

/// True when a `requires` entry of `source` for `target` has a symbol port.
fn symbol_port(source: &Component, target: &Component) -> bool {
    source.requires().iter().flatten().any(|entry| {
        entry.component() == target.label()
            && entry
                .through()
                .iter()
                .any(|port| port.as_text().contains(':'))
    })
}

/// `requires_import_assessment`: a wildcard import cannot prove an exact symbol port.
fn assessment(source: &Component, target: &Component, import: &Import) -> Judged {
    let named = import.symbols_known()
        && (!import.under_type_checking() || import.symbol().is_none())
        && import.symbol() != Some("*");
    let symbol = if named { import.symbol() } else { None };
    let module = import.target_module();
    let entries = || {
        source
            .requires()
            .iter()
            .flatten()
            .filter(|entry| entry.component() == target.label())
    };
    let covered = entries().any(|entry| {
        entry.through().is_empty()
            || entry
                .through()
                .iter()
                .any(|port| port_judged(port.as_text(), module, symbol, true) == Judged::Pass)
    });
    if covered {
        return Judged::Pass;
    }
    let undecided = !named
        && entries().any(|entry| {
            entry.through().iter().any(|port| {
                port_judged(port.as_text(), module, import.symbol(), false) == Judged::Undecided
            })
        });
    if undecided {
        Judged::Undecided
    } else {
        Judged::Fail
    }
}

/// `_required_port_assessment`: a module prefix, or an exact `module:symbol` port.
fn port_judged(port: &str, module: &str, symbol: Option<&str>, known: bool) -> Judged {
    let Some((port_module, port_symbol)) = port.split_once(':') else {
        return if in_scope(module, port) {
            Judged::Pass
        } else {
            Judged::Fail
        };
    };
    if module != port_module {
        Judged::Fail
    } else if !known {
        Judged::Undecided
    } else if symbol == Some(port_symbol) {
        Judged::Pass
    } else {
        Judged::Fail
    }
}

/// The number of undecided positions in judgements (`symbol_limits`).
pub(crate) fn undecided(judged: impl Iterator<Item = Judged>) -> usize {
    judged.filter(|judged| *judged == Judged::Undecided).count()
}
