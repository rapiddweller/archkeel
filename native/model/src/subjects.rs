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

use archkeel_contract::{Component, ForbiddenDependency, Rule, Selector, TargetKind};

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
    /// The source subjects: the modules of the reply (of the domain of a mount) and the planned
    /// modules of the components.
    pub(crate) subjects: Vec<&'a str>,
    /// The target subjects: every module of the reply and the planned modules of the components.
    pub(crate) targets: Vec<&'a str>,
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
    let count = |selectors: &[&str]| any_in(&names.subjects, selectors);
    let sides: Vec<Vec<&str>> = match rule {
        Rule::ForbiddenDependency(rule) => return forbidden(rule, components, names),
        // `_rule_subject_matches`: a target side reads every module, each other side the source
        // subjects.
        Rule::AllowedDependency(rule) => {
            let found = count(&[rule.source().as_text()])
                && any_in(&names.targets, &[rule.target().as_text()]);
            return if found {
                Subjects::Found
            } else {
                Subjects::Missing
            };
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
        // `rule_scopes` gives these kinds no side.
        Rule::CompleteRequires(_)
        | Rule::LayerOrder(_)
        | Rule::NoComponentCycles(_)
        | Rule::InterfaceBoundary(_)
        | Rule::CallOwner(_) => Vec::new(),
        // The profile-limited kinds: the scope state stops at their limit before this check
        // (`limits.rs`); a kind here never reaches a PASS.
        Rule::ForbiddenCallArgument(_)
        | Rule::CatalogArgument(_)
        | Rule::CatalogUse(_)
        | Rule::ForbiddenEffectUnderCondition(_)
        | Rule::SourceOwnership(_)
        | Rule::SymbolPlacement(_)
        | Rule::BoundaryTypes(_)
        | Rule::BoundedNumericOperand(_)
        | Rule::ProtocolDeclarations(_) => return Subjects::Unread,
    };
    if sides.iter().all(|side| count(side)) {
        Subjects::Found
    } else {
        Subjects::Missing
    }
}

/// True when a name lies in the scope of a selector.
fn any_in(names: &[&str], selectors: &[&str]) -> bool {
    names
        .iter()
        .any(|module| selectors.iter().any(|scope| in_scope(module, scope)))
}

fn texts(selectors: &[Selector]) -> Vec<&str> {
    selectors.iter().map(Selector::as_text).collect()
}

/// `forbidden_dependency`: the sides of `DependencySelector.select`. A target that names a
/// builtin target or an import namespace has no target side.
fn forbidden(rule: &ForbiddenDependency, components: &[Component], names: &Names<'_>) -> Subjects {
    let [source, target] = crate::selection::dependency_sides(rule, components);
    let target_side = !(*rule.target_kind() == TargetKind::ImportNamespace
        || names
            .builtins
            .iter()
            .any(|name| name == rule.target().as_text()));
    let found = |selection: &crate::selection::Selection<'_>, among: &[&str]| {
        among.iter().any(|m| selection.matches(m))
    };
    if found(&source, &names.subjects) && (!target_side || found(&target, &names.targets)) {
        Subjects::Found
    } else {
        Subjects::Missing
    }
}

#[cfg(test)]
#[path = "subjects_tests.rs"]
mod tests;
