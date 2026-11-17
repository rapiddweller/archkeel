// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The premises that a PASS rests on (AD-764): the one seam for every claim of the contract about
//! what the scan cannot see.
//!
//! A premise is never a proof. A rule that passes only because of one reads "PASS assuming
//! <premise>". Three kinds exist:
//! - the declared reach of a door site (`declarations.door_reach`, AD-664);
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
    /// The declared reach of a door site; the subject is the site.
    DoorReach,
    /// A stated user outside the scan of a public item; the subject is `module:name`.
    ExternalUser,
    /// A premise that the contract declares by name; the subject names what it covers.
    Declared(PremiseName),
}

impl PremiseKind {
    /// The word of the kind in the frame.
    pub fn kind_word(self) -> &'static str {
        match self {
            PremiseKind::DoorReach => "door_reach",
            PremiseKind::ExternalUser => "external_user",
            PremiseKind::Declared(name) => PremiseName::premise_word(name),
        }
    }

    /// The kind of a word of the frame, or `None` for a word that names no kind.
    pub fn of_kind_word(word: &str) -> Option<PremiseKind> {
        let mut kinds = vec![PremiseKind::DoorReach, PremiseKind::ExternalUser];
        for name in PremiseName::ALL {
            kinds.push(PremiseKind::Declared(name));
        }
        let mut found = None;
        for kind in kinds {
            if PremiseKind::kind_word(kind) == word {
                found = Some(kind);
            }
        }
        found
    }
}

/// One premise that the PASS of a rule rests on.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct UsedPremise {
    /// What the premise is.
    pub kind: PremiseKind,
    /// The site, the item or the scope that the premise covers.
    pub subject: String,
}

/// The premises that a PASS of `rule` in `model` rests on, in a fixed order: the door sites, the
/// stated external users, then the declared premises.
pub fn rule_premises(model: &Model, rule: &Rule) -> Vec<UsedPremise> {
    let mut found: Vec<UsedPremise> = Vec::new();
    let doors: Vec<&Applied> = crate::gap_effects::assumed(model, rule);
    for door in doors {
        let subject = Applied::site(door);
        found.push(UsedPremise {
            kind: PremiseKind::DoorReach,
            subject,
        });
    }
    if let Rule::UnusedPublic(unused) = rule {
        let items: Vec<&PublicItem> = crate::published::stated_users(model, unused);
        for item in items {
            let subject = format!("{}:{}", item.module, item.name);
            found.push(UsedPremise {
                kind: PremiseKind::ExternalUser,
                subject,
            });
        }
    }
    found.extend(declared(model, rule));
    found
}

/// The declared premises that `rule` rests on. No rule reads one yet: the first one,
/// `standard_library_unchanged`, comes with #1538.
fn declared(model: &Model, rule: &Rule) -> Vec<UsedPremise> {
    let _ = (model, rule);
    Vec::new()
}

impl Model {
    /// Whether the contract declares the premise `name` (`declarations.premises`).
    pub fn declares_premise(&self, name: PremiseName) -> bool {
        let declared: Vec<PremiseName> = archkeel_contract::declared_premises(self.contract());
        declared.contains(&name)
    }
}

/// The premises of a run in words, or `None` without one: `the declared reach of N doors`,
/// `N stated external users`, then the words of each declared premise, joined by `and`. `doors`
/// is the number of applied door declarations; `used` is each premise of each PASS rule. The one
/// place of these words.
pub fn premise_words(doors: usize, used: &[(PremiseKind, &str)]) -> Option<String> {
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
            PremiseKind::DoorReach => {}
        }
    }
    let mut parts: Vec<String> = Vec::new();
    if doors > 0 {
        parts.push(format!(
            "the declared reach of {doors} door{}",
            plural(doors)
        ));
    }
    let count = BTreeSet::len(&users);
    if count > 0 {
        parts.push(format!("{count} stated external user{}", plural(count)));
    }
    for name in declared {
        parts.push(PremiseName::assumption_words(name).to_owned());
    }
    (!parts.is_empty()).then(|| parts.join(" and "))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn each_kind_has_one_word_and_the_words_of_a_run_name_each_premise() {
        for kind in [
            PremiseKind::DoorReach,
            PremiseKind::ExternalUser,
            PremiseKind::Declared(PremiseName::StandardLibraryUnchanged),
        ] {
            assert_eq!(PremiseKind::of_kind_word(kind.kind_word()), Some(kind));
        }
        assert_eq!(PremiseKind::of_kind_word("other"), None);
        assert_eq!(premise_words(0, &[]), None);
        assert_eq!(
            premise_words(1, &[(PremiseKind::DoorReach, "D")]).as_deref(),
            Some("the declared reach of 1 door")
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
                "the declared reach of 2 doors and 2 stated external users and an unchanged \
                 standard library"
            )
        );
    }
}
