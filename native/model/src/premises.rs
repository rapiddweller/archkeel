// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The premises that a PASS rests on (AD-764): the one seam for every claim of the contract about
//! what the scan cannot see.
//!
//! A premise is never a proof. A rule that passes only because of one reads "PASS under
//! <premise>". Three kinds exist:
//! - the declared reach of a trojan horse site (`declarations.trojan_horse_reach`, AD-664);
//! - a stated external user of a public item (`external_users` of `unused_public`, AD-670);
//! - a premise that the contract declares by name (`declarations.premises`, contract 3.17.0).
//!
//! `rule_premises` lists the premises of one rule; the report writes them in the frame and
//! `premise_words` gives the words of the run. A new declared premise is a variant of
//! `PremiseName` in the contract and one branch in `declared` below: the branch returns, for the
//! rule, each subject whose gap the premise cancels, and the place that cancels the gap asks
//! `declares_premise` first.

use std::collections::BTreeSet;

use archkeel_contract::{PremiseName, Rule};

use crate::door_reach::Applied;
use crate::model::Model;
use crate::published_items::PublicItem;

/// What one premise is.
#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord)]
pub enum PremiseKind {
    /// The declared reach of a trojan horse site; the subject is the site.
    TrojanHorseReach,
    /// A stated user outside the scan of a public item; the subject is `module:name`.
    ExternalUser,
    /// A premise that the contract declares by name; the subject names what it covers.
    Declared(PremiseName),
}

/// The word of a premise kind in the frame.
pub fn kind_word(kind: PremiseKind) -> &'static str {
    match kind {
        PremiseKind::TrojanHorseReach => "trojan_horse_reach",
        PremiseKind::ExternalUser => "external_user",
        PremiseKind::Declared(name) => archkeel_contract::premise_word(name),
    }
}

/// The premise kind of a word of the frame, or `None` for a word that names no kind.
pub fn of_kind_word(word: &str) -> Option<PremiseKind> {
    let fixed = [PremiseKind::TrojanHorseReach, PremiseKind::ExternalUser];
    let declared = archkeel_contract::PREMISE_NAMES.map(PremiseKind::Declared);
    fixed
        .into_iter()
        .chain(declared)
        .find(|kind| kind_word(*kind) == word)
}

/// One premise that the PASS of a rule rests on.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct UsedPremise {
    /// What the premise is.
    pub kind: PremiseKind,
    /// The site, the item or the scope that the premise covers.
    pub subject: String,
}

/// The premises that a PASS of `rule` in `model` rests on, in a fixed order: the trojan horse sites, the
/// stated external users, then the declared premises.
pub fn rule_premises(model: &Model, rule: &Rule) -> Vec<UsedPremise> {
    let trojan_horses: Vec<&Applied> = crate::gap_effects::assumed(model, rule);
    let trojan_horses = trojan_horses.into_iter().map(|trojan_horse| UsedPremise {
        kind: PremiseKind::TrojanHorseReach,
        subject: Applied::site(trojan_horse),
    });
    let items: Vec<&PublicItem> = match rule {
        Rule::UnusedPublic(unused) => crate::published::stated_users(model, unused),
        _ => Vec::new(),
    };
    let users = items.into_iter().map(|item| UsedPremise {
        kind: PremiseKind::ExternalUser,
        subject: format!("{}:{}", item.module, item.name),
    });
    trojan_horses
        .chain(users)
        .chain(declared(model, rule))
        .collect()
}

/// The declared premises that `rule` rests on: `standard_library_unchanged` for each position or
/// entry of a `boundary_types` rule that it allows (AD-782).
fn declared(model: &Model, rule: &Rule) -> Vec<UsedPremise> {
    // AD-1047: a rule that reads module pair gaps can rest on the compiler type reach, when the contract
    // declares it. The rule says so although no gap was dropped: the claim is only stronger.
    let reads_pairs = matches!(
        rule,
        Rule::ForbiddenDependency(_)
            | Rule::SiblingIsolation(_)
            | Rule::LayerOrder(_)
            | Rule::CompleteRequires(_)
            | Rule::NoComponentCycles(_)
            | Rule::InterfaceBoundary(_)
    );
    // The contract declares the premise and the reply proves that the facts were used (AD-1114): the
    // declaration alone is a wish, not evidence.
    if reads_pairs
        && Model::declares_premise(model, PremiseName::RustTypeReach)
        && model.graph().observed().type_reach.is_some()
    {
        return vec![UsedPremise {
            kind: PremiseKind::Declared(PremiseName::RustTypeReach),
            subject: "type reach".to_owned(),
        }];
    }
    if let Rule::ForbiddenConstruct(rule) = rule {
        let Ok(Some(subject)) = crate::construct_match::receipt(model, rule) else {
            return Vec::new();
        };
        if Model::declares_premise(model, PremiseName::StandardLibraryUnchanged) {
            return vec![UsedPremise {
                kind: PremiseKind::Declared(PremiseName::StandardLibraryUnchanged),
                subject: str::to_owned(subject),
            }];
        }
        return Vec::new();
    }
    if let Rule::ProtocolDeclarations(rule) = rule {
        return vec![UsedPremise {
            kind: PremiseKind::Declared(PremiseName::StandardLibraryUnchanged),
            subject: rule.protocol().as_text().to_owned(),
        }];
    }
    let Rule::BoundaryTypes(rule) = rule else {
        return Vec::new();
    };
    let Ok(reading) = crate::boundary_positions::read(model, rule) else {
        return Vec::new();
    };
    let used = |subject: String| UsedPremise {
        kind: PremiseKind::Declared(PremiseName::StandardLibraryUnchanged),
        subject,
    };
    IntoIterator::into_iter(reading.assumed).map(used).collect()
}

impl Model {
    /// Whether the contract declares the premise `name` (`declarations.premises`).
    pub fn declares_premise(&self, name: PremiseName) -> bool {
        let declared: Vec<PremiseName> = archkeel_contract::declared_premises(self.contract());
        declared.contains(&name)
    }
}

/// The premises of a run in words, or `None` without one: `N declared reaches`,
/// `N stated external users`, then the words of each declared premise, joined by `and`. `trojan_horses`
/// is the number of applied trojan horse declarations; `used` is each premise of each PASS rule. The one
/// place of these words.
pub fn premise_words(trojan_horses: usize, used: &[(PremiseKind, &str)]) -> Option<String> {
    let plural = |n: usize| if n == 1 { "" } else { "s" };
    let mut users: BTreeSet<&str> = BTreeSet::new();
    let mut declared: BTreeSet<PremiseName> = BTreeSet::new();
    for (kind, subject) in used {
        match kind {
            PremiseKind::ExternalUser => {
                users.insert(subject);
            }
            PremiseKind::Declared(name) => {
                declared.insert(*name);
            }
            PremiseKind::TrojanHorseReach => {}
        }
    }
    let count = BTreeSet::len(&users);
    let trojan_horse_words = (trojan_horses > 0).then(|| {
        format!(
            "{trojan_horses} declared reach{}",
            if trojan_horses == 1 { "" } else { "es" }
        )
    });
    let user_words = (count > 0).then(|| format!("{count} stated external user{}", plural(count)));
    let declared_words = declared
        .into_iter()
        .map(|name| archkeel_contract::assumption_words(name).to_owned());
    let parts: Vec<String> = trojan_horse_words
        .into_iter()
        .chain(user_words)
        .chain(declared_words)
        .collect();
    match parts.as_slice() {
        [] => None,
        [_, ..] => Some(parts.join(" and ")),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn each_kind_has_one_word_and_the_words_of_a_run_name_each_premise() {
        for kind in [
            PremiseKind::TrojanHorseReach,
            PremiseKind::ExternalUser,
            PremiseKind::Declared(PremiseName::StandardLibraryUnchanged),
        ] {
            assert_eq!(of_kind_word(kind_word(kind)), Some(kind));
        }
        assert_eq!(of_kind_word("other"), None);
        assert_eq!(premise_words(0, &[]), None);
        assert_eq!(
            premise_words(1, &[(PremiseKind::TrojanHorseReach, "D")]).as_deref(),
            Some("1 declared reach")
        );
        let used = [
            (PremiseKind::ExternalUser, "a:x"),
            (PremiseKind::ExternalUser, "a:x"),
            (PremiseKind::ExternalUser, "a:y"),
            (
                PremiseKind::Declared(PremiseName::StandardLibraryUnchanged),
                "app",
            ),
        ];
        assert_eq!(
            premise_words(2, &used).as_deref(),
            Some(
                "2 declared reaches and 2 stated external users and the premise that \
                 outside code leaves the standard library unchanged"
            )
        );
    }

    #[test]
    fn the_premise_word_of_the_facts_is_the_word_of_the_contract() {
        assert_eq!(
            archkeel_facts::type_reach::PREMISE,
            archkeel_contract::premise_word(PremiseName::RustTypeReach)
        );
    }
}
