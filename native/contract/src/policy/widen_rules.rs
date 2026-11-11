// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The widenings of rules (Python `ir/widening_rules.py`) and the rule part of
//! `contract_narrowing_changes`. A kind without a classifier fails closed: any difference of the
//! whole rule widens.

use std::collections::BTreeMap;

use crate::model::{RuleKind, SelectorMatch, TargetKind};
use crate::policy::change::{set_widenings, ChangeKind, ContractChange};
use crate::policy::pyrepr::{texts, word};
use crate::policy::reference::python_repr;
use crate::policy::widen_rule_parts::{
    allowance, cycles, gained, generic, new_entries, relaxed, sources,
};
use crate::rule::{head_of, kind_of, Rule};

/// Python `_matched_rule_widenings` for two rules of one kind.
#[expect(
    clippy::too_many_lines,
    reason = "one arm for each of the 22 rule kinds, as in Python"
)]
fn matched(subject: &str, before: &Rule, after: &Rule) -> Vec<ContractChange> {
    use Rule as R;
    match (before, after) {
        (R::ForbiddenDependency(old), R::ForbiddenDependency(new)) => {
            let mut changes = set_widenings(
                subject,
                "allowed_sources",
                texts(&old.allowed_sources),
                texts(&new.allowed_sources),
                true,
            );
            changes.extend(relaxed(
                subject,
                old.include_type_checking,
                new.include_type_checking,
            ));
            for (name, was, now) in [
                ("source_match", old.source_match, new.source_match),
                ("target_match", old.target_match, new.target_match),
            ] {
                if was == SelectorMatch::Prefix && now == SelectorMatch::Exact {
                    let message = format!("{subject}.{name} narrowed from prefix to exact");
                    changes.push(ContractChange::widened(
                        ChangeKind::MatchNarrowed,
                        subject,
                        name,
                        message,
                    ));
                }
            }
            if old.target_kind == TargetKind::Module
                && new.target_kind == TargetKind::ImportNamespace
            {
                let message = format!("{subject} now permits an absent import namespace");
                changes.push(ContractChange::widened(
                    ChangeKind::AbsentNamespace,
                    subject,
                    "target_kind",
                    message,
                ));
            }
            let handled = [
                "allowed_sources",
                "include_type_checking",
                "source_match",
                "target_match",
                "target_kind",
            ];
            changes.extend(generic(subject, before, after, &handled));
            changes
        }
        (R::ForbiddenConstruct(old), R::ForbiddenConstruct(new)) => {
            let words = |items: &[crate::model::ConstructKind]| -> Vec<String> {
                items.iter().map(word).collect()
            };
            let (was, now) = (words(&old.constructs), words(&new.constructs));
            let mut changes = set_widenings(subject, "constructs", texts(&was), texts(&now), false);
            for (name, was, now) in [
                (
                    "allowed_sources",
                    &old.allowed_sources,
                    &new.allowed_sources,
                ),
                ("exact_sources", &old.exact_sources, &new.exact_sources),
            ] {
                changes.extend(set_widenings(subject, name, texts(was), texts(now), true));
            }
            let ignores = new_entries(&old.allowed_type_ignores, &new.allowed_type_ignores);
            let mut ignores: Vec<String> = ignores
                .into_iter()
                .map(|item| {
                    format!(
                        "TypeIgnoreAllowance(qualified_name={}, line={}, statement={}, tag={})",
                        python_repr(&item.qualified_name.0),
                        item.line,
                        python_repr(&item.statement),
                        python_repr(&item.tag)
                    )
                })
                .collect();
            ignores.sort();
            changes.extend(gained(subject, "allowed_type_ignores", ignores));
            let handled = [
                "constructs",
                "allowed_sources",
                "exact_sources",
                "allowed_type_ignores",
            ];
            changes.extend(generic(subject, before, after, &handled));
            changes
        }
        (R::ExternalDependencyScope(old), R::ExternalDependencyScope(new)) => sources(
            subject,
            before,
            after,
            [&old.allowed_sources, &new.allowed_sources],
            [&old.exact_sources, &new.exact_sources],
        ),
        (R::CallOwner(old), R::CallOwner(new)) => sources(
            subject,
            before,
            after,
            [&old.allowed_sources, &new.allowed_sources],
            [&old.exact_sources, &new.exact_sources],
        ),
        (R::CompleteRequires(old), R::CompleteRequires(new)) => {
            let mut changes = relaxed(
                subject,
                old.include_type_checking,
                new.include_type_checking,
            );
            changes.extend(generic(subject, before, after, &["include_type_checking"]));
            changes
        }
        (R::RootLayout(old), R::RootLayout(new)) => {
            let mut changes = set_widenings(
                subject,
                "allowed_children",
                texts(&old.allowed_children),
                texts(&new.allowed_children),
                true,
            );
            changes.extend(generic(subject, before, after, &["allowed_children"]));
            changes
        }
        (R::InterfaceBoundary(old), R::InterfaceBoundary(new)) => {
            let none = Vec::new();
            let grants = new_entries(
                old.module_object_grants.as_ref().unwrap_or(&none),
                new.module_object_grants.as_ref().unwrap_or(&none),
            );
            let mut keyed: Vec<(&str, &str)> = grants
                .iter()
                .map(|item| (item.source_module.0.as_str(), item.target_module.0.as_str()))
                .collect();
            keyed.sort_unstable();
            let texts = keyed
                .into_iter()
                .map(|(source, target)| {
                    let (source, target) = (python_repr(source), python_repr(target));
                    format!("ModuleObjectGrant(source_module={source}, target_module={target})")
                })
                .collect();
            let mut changes = gained(subject, "module_object_grants", texts);
            changes.extend(relaxed(
                subject,
                old.include_type_checking,
                new.include_type_checking,
            ));
            changes.extend(generic(
                subject,
                before,
                after,
                &["include_type_checking", "module_object_grants"],
            ));
            changes
        }
        (R::SiblingIsolation(old), R::SiblingIsolation(new)) => {
            let mut changes = set_widenings(
                subject,
                "members",
                texts(&old.members),
                texts(&new.members),
                false,
            );
            changes.extend(relaxed(
                subject,
                old.include_type_checking,
                new.include_type_checking,
            ));
            changes.extend(generic(
                subject,
                before,
                after,
                &["members", "include_type_checking"],
            ));
            changes
        }
        (R::BoundaryTypes(old), R::BoundaryTypes(new)) => {
            let found = new_entries(&old.allowed_positions, &new.allowed_positions);
            let mut changes = gained(
                subject,
                "allowed_positions",
                found.into_iter().map(allowance).collect(),
            );
            changes.extend(generic(subject, before, after, &["allowed_positions"]));
            changes
        }
        (R::BoundedNumericOperand(old), R::BoundedNumericOperand(new)) => {
            let mut changes = Vec::new();
            if new.minimum_value < old.minimum_value {
                let message = format!(
                    "{subject}.minimum_value decreased from {} to {}",
                    old.minimum_value, new.minimum_value
                );
                changes.push(ContractChange::widened(
                    ChangeKind::Raised,
                    subject,
                    "minimum_value",
                    message,
                ));
            }
            changes.extend(generic(subject, before, after, &["minimum_value"]));
            changes
        }
        (R::NoComponentCycles(old), R::NoComponentCycles(new)) => {
            cycles(subject, before, after, old, new)
        }
        (R::AllowedDependency(_), R::AllowedDependency(_))
        | (R::ForbiddenCallArgument(_), R::ForbiddenCallArgument(_))
        | (R::SourceOwnership(_), R::SourceOwnership(_))
        | (R::CompleteAssignment(_), R::CompleteAssignment(_))
        | (R::CompleteExternalScope(_), R::CompleteExternalScope(_)) => {
            generic(subject, before, after, &[])
        }
        _ => not_enumerated(subject, before, after),
    }
}

/// Fail closed: any difference of a rule without a classifier widens, also of its rationale.
fn not_enumerated(subject: &str, before: &Rule, after: &Rule) -> Vec<ContractChange> {
    if before == after {
        return Vec::new();
    }
    let message = format!("{subject} changed in a way this comparison does not enumerate");
    vec![ContractChange::widened(
        ChangeKind::NotEnumerated,
        subject,
        "rule",
        message,
    )]
}

/// Whether Python `_matched_rule_widenings` has a classifier for the kind. The match names each
/// kind, so a new kind does not compile without a decision.
fn classified(kind: RuleKind) -> bool {
    use RuleKind as K;
    match kind {
        K::ForbiddenDependency
        | K::AllowedDependency
        | K::ForbiddenConstruct
        | K::ExternalDependencyScope
        | K::CallOwner
        | K::ForbiddenCallArgument
        | K::CompleteRequires
        | K::RootLayout
        | K::InterfaceBoundary
        | K::SiblingIsolation
        | K::BoundaryTypes
        | K::SourceOwnership
        | K::CompleteAssignment
        | K::CompleteExternalScope
        | K::BoundedNumericOperand
        | K::NoComponentCycles => true,
        K::CatalogArgument
        | K::CatalogUse
        | K::ForbiddenEffectUnderCondition
        | K::LayerOrder
        | K::SymbolPlacement
        | K::ProtocolDeclarations => false,
    }
}

/// Python `_rule_presence_widening`: a permission added or a restriction removed widens.
fn presence(rule: &Rule, added: bool) -> Option<ContractChange> {
    let permission = kind_of(rule) == RuleKind::AllowedDependency;
    if permission != added {
        return None;
    }
    let subject = format!("rule {}", head_of(rule).id.0);
    let verb = if added { "added" } else { "removed" };
    let message = format!("{subject} ({}) {verb}", word(&kind_of(rule)));
    Some(ContractChange::widened(
        ChangeKind::Presence,
        &subject,
        "presence",
        message,
    ))
}

fn by_id(rules: &[Rule]) -> BTreeMap<&str, &Rule> {
    rules
        .iter()
        .map(|rule| (head_of(rule).id.0.as_str(), rule))
        .collect()
}

/// Python `rules_widenings`: rules matched by ID.
pub(crate) fn rules_widenings(before: &[Rule], after: &[Rule]) -> Vec<ContractChange> {
    let (old, new) = (by_id(before), by_id(after));
    let mut changes: Vec<ContractChange> = new
        .iter()
        .filter(|(id, _)| !old.contains_key(*id))
        .filter_map(|(_, rule)| presence(rule, true))
        .collect();
    changes.extend(
        old.iter()
            .filter(|(id, _)| !new.contains_key(*id))
            .filter_map(|(_, rule)| presence(rule, false)),
    );
    for (id, rule) in &old {
        let Some(other) = new.get(id) else {
            continue;
        };
        let subject = format!("rule {id}");
        if kind_of(rule) == kind_of(other) && classified(kind_of(rule)) {
            changes.extend(matched(&subject, rule, other));
        } else if kind_of(rule) == kind_of(other) {
            changes.extend(not_enumerated(&subject, rule, other));
        } else {
            let message = format!(
                "{subject} changed kind from {} to {}",
                word(&kind_of(rule)),
                word(&kind_of(other))
            );
            changes.push(ContractChange::widened(
                ChangeKind::KindChanged,
                &subject,
                "kind",
                message,
            ));
        }
    }
    changes
}

/// The rule part of Python `contract_narrowing_changes`: a restriction added, a permission
/// removed.
pub(crate) fn rules_narrowings(before: &[Rule], after: &[Rule]) -> Vec<ContractChange> {
    let (old, new) = (by_id(before), by_id(after));
    let narrowing = |rule: &Rule, verb: &str| {
        let subject = format!("rule {}", head_of(rule).id.0);
        let message = format!("{subject} ({}) {verb}", word(&kind_of(rule)));
        ContractChange::narrowed(ChangeKind::Presence, &subject, "presence", message)
    };
    let mut changes: Vec<ContractChange> = new
        .iter()
        .filter(|(id, rule)| !old.contains_key(*id) && kind_of(rule) != RuleKind::AllowedDependency)
        .map(|(_, rule)| narrowing(rule, "added"))
        .collect();
    changes.extend(
        old.iter()
            .filter(|(id, rule)| {
                !new.contains_key(*id) && kind_of(rule) == RuleKind::AllowedDependency
            })
            .map(|(_, rule)| narrowing(rule, "removed")),
    );
    changes
}
