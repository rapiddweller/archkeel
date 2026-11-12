// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The subject check of every rule of the contract (slice S4).
//!
//! Reference engine: `check/evaluation/rules.py` `rule_subject_failures` with `rule_scopes`,
//! `_rule_source_subjects`, `_planned_subject_modules` and `_rule_subject_matches`, and
//! `ir/dependency.py` `DependencySelector.select` for `forbidden_dependency`. A rule side that
//! matches no module of the reply and no planned module is a coverage failure: the observation
//! is not complete, so no rule of the run passes.
//!
//! The kinds that the store-accepted profiles cannot decide are profile limits (`limits.rs`),
//! and the reference engine leaves them out of this check. For `forbidden_construct` the
//! reference engine adds the classes and functions of the symbols to the subjects. A count above
//! zero is final without them; a count of zero is not read, so the rule gives no PASS.

use std::collections::HashMap;

use archkeel_contract::{
    Component, ForbiddenDependency, Rule, Selector, SelectorMatch, TargetKind,
};

use crate::ownership::in_scope;

/// The result of the subject check of one rule.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum Subjects {
    /// Each side of the rule matches a subject, or the rule has no side.
    Found,
    /// A side matches no subject: a coverage failure of the reference engine.
    Missing,
    /// The core cannot count the subjects of a side: the symbols can add one.
    Unread,
}

/// The names that a rule side can match, and the names of the builtin targets of the reply.
pub(crate) struct Names<'a> {
    /// The modules of the reply and the planned modules of the components.
    pub(crate) subjects: Vec<&'a str>,
    /// The names of the builtin import targets: a `forbidden_dependency` target of this name is
    /// a subject that no scan lists as a module.
    pub(crate) builtins: &'a [String],
}

/// The planned modules of the components (`_planned_subject_modules`): the part of each
/// `planned` entry before a colon.
pub(crate) fn planned(components: &[Component]) -> impl Iterator<Item = &str> {
    components
        .iter()
        .flat_map(|component| component.planned().iter().flatten())
        .map(|entry| entry.as_text().split(':').next().unwrap_or_default())
}

/// The subject check of one rule.
pub(crate) fn check(rule: &Rule, components: &[Component], names: &Names<'_>) -> Subjects {
    let count = |selectors: &[&str]| {
        names
            .subjects
            .iter()
            .any(|module| selectors.iter().any(|scope| in_scope(module, scope)))
    };
    let sides: Vec<Vec<&str>> = match rule {
        Rule::ForbiddenDependency(rule) => return forbidden(rule, components, names),
        Rule::AllowedDependency(rule) => {
            vec![vec![rule.source().as_text()], vec![rule.target().as_text()]]
        }
        Rule::ExternalDependencyScope(rule) => [rule.allowed_sources(), rule.exact_sources()]
            .into_iter()
            .filter(|side| !side.is_empty())
            .map(|side| texts(side))
            .collect(),
        Rule::SiblingIsolation(rule) => vec![texts(rule.members())],
        Rule::CompleteAssignment(rule) | Rule::CompleteExternalScope(rule) => {
            vec![vec![rule.source().as_text()]]
        }
        Rule::RootLayout(rule) => vec![vec![rule.root().as_text()]],
        Rule::ForbiddenConstruct(rule) => {
            return if count(&[rule.source().as_text()]) {
                Subjects::Found
            } else {
                Subjects::Unread
            };
        }
        // `rule_scopes` gives these kinds no side; the profile-limited kinds are not checked.
        _ => Vec::new(),
    };
    if sides.iter().all(|side| count(side)) {
        Subjects::Found
    } else {
        Subjects::Missing
    }
}

fn texts(selectors: &[Selector]) -> Vec<&str> {
    selectors.iter().map(Selector::as_text).collect()
}

/// The module selection of one side: packages and exact modules (`ModuleSelection`).
struct Selection<'a> {
    packages: Vec<&'a str>,
    exact: Vec<&'a str>,
}

impl Selection<'_> {
    fn matches(&self, module: &str) -> bool {
        self.exact.contains(&module) || self.packages.iter().any(|p| in_scope(module, p))
    }
}

/// `forbidden_dependency`: the sides of `DependencySelector.select`. A target that names a
/// builtin target or an import namespace has no target side.
fn forbidden(rule: &ForbiddenDependency, components: &[Component], names: &Names<'_>) -> Subjects {
    let (source, target) = selections(rule, components);
    let target_side = !(*rule.target_kind() == TargetKind::ImportNamespace
        || names
            .builtins
            .iter()
            .any(|name| name == rule.target().as_text()));
    let found = |selection: &Selection<'_>| names.subjects.iter().any(|m| selection.matches(m));
    if found(&source) && (!target_side || found(&target)) {
        Subjects::Found
    } else {
        Subjects::Missing
    }
}

/// The source and target selections of a `forbidden_dependency` rule.
fn selections<'a>(
    rule: &'a ForbiddenDependency,
    components: &'a [Component],
) -> (Selection<'a>, Selection<'a>) {
    let source = rule.source().as_text();
    let target = rule.target().as_text();
    let whole = rule.target_symbol().is_none()
        && *rule.source_match() == SelectorMatch::Prefix
        && *rule.target_match() == SelectorMatch::Prefix
        && *rule.target_kind() == TargetKind::Module;
    if whole {
        // `component_pair`: one owner label each, by an exact package; the last component of a
        // label gives its modules.
        let owners_of = |name: &str| {
            let mut labels: Vec<&str> = components
                .iter()
                .filter(|component| component.packages().iter().any(|p| p.as_text() == name))
                .map(|component| component.label().as_text())
                .collect();
            labels.dedup();
            labels.sort_unstable();
            labels.dedup();
            labels
        };
        if let ([source_label], [target_label]) =
            (owners_of(source).as_slice(), owners_of(target).as_slice())
        {
            let by_label: HashMap<&str, &Component> = components
                .iter()
                .map(|component| (component.label().as_text(), component))
                .collect();
            if let (Some(source), Some(target)) =
                (by_label.get(source_label), by_label.get(target_label))
            {
                return (owned(source), owned(target));
            }
        }
    }
    (
        literal(source, *rule.source_match()),
        literal(target, *rule.target_match()),
    )
}

fn owned(component: &Component) -> Selection<'_> {
    Selection {
        packages: component.packages().iter().map(|p| p.as_text()).collect(),
        exact: component
            .exact_modules()
            .iter()
            .map(|p| p.as_text())
            .collect(),
    }
}

fn literal(name: &str, mode: SelectorMatch) -> Selection<'_> {
    match mode {
        SelectorMatch::Exact => Selection {
            packages: Vec::new(),
            exact: vec![name],
        },
        SelectorMatch::Prefix => Selection {
            packages: vec![name],
            exact: Vec::new(),
        },
    }
}

#[cfg(test)]
#[path = "subjects_tests.rs"]
mod tests;
