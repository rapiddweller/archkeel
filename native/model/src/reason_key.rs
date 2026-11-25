// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The stable key of a reason (AD-546).
//!
//! A baseline accepts an UNKNOWN by WHAT it is: a kind, a subject and a reason. The display text
//! of a `Reason` is not that: it can hold a count, a position or a pointer that moves with an
//! unrelated edit. This module writes the key from the typed values.
//!
//! Each match lists every variant and has no wildcard: a new reason does not compile here until
//! its key is decided. A key never holds a line, an evidence id, a digest or a sum of other
//! entries. A number is allowed only as the multiplicity of an entry that no other entry counts.

#![deny(
    clippy::wildcard_enum_match_arm,
    clippy::match_wildcard_for_single_variants
)]

use crate::causes::{Cause, Held, Part};
use crate::coverage::Incomplete;
use crate::reason::{Hygiene, Input, Reason, Refusal, UmlGap, Unsupported};

/// One entry of the stable key of a reason.
#[derive(Clone, Debug, PartialEq, Eq, PartialOrd, Ord)]
pub struct Stable {
    /// The kind word. It is the `GapKind` word of the shell where one exists.
    pub kind: String,
    /// The subject, or `None` when the subject is the id of the rule row that holds the reason.
    pub subject: Option<String>,
    /// The code of the cause and the value that names it.
    pub reason: String,
    /// How many times the entry occurs. At least 1.
    pub count: u64,
}

impl Stable {
    fn of(kind: &str, reason: impl Into<String>) -> Stable {
        Stable {
            kind: kind.to_owned(),
            subject: None,
            reason: reason.into(),
            count: 1,
        }
    }

    fn many(mut self, count: usize) -> Stable {
        self.count = u64::try_from(count).unwrap_or(u64::MAX).max(1);
        self
    }
}

/// The `GapKind` word of the gap that a reason makes in the frame (AD-546). The shell reads the
/// word and does not infer it from the text. A part that has no word of its own in the shell is
/// `other`, as it was when the shell read the text.
pub fn gap_kind(reason: &Reason) -> &'static str {
    match reason {
        Reason::Unsupported(part) => unsupported_kind(part),
        Reason::MissingInput(_) => "reply_refused",
        Reason::Hygiene(found) => found.code(),
        Reason::TooManyRows(_)
        | Reason::Interface(_)
        | Reason::Incomplete(_)
        | Reason::NoSubjects
        | Reason::UncitedChild(_)
        | Reason::Refused(_)
        | Reason::NotComplete(_)
        | Reason::Uml(_) => "other",
    }
}

/// The entries of the stable key of a reason: one for most reasons, one for each pair of a pair
/// gap, and one for each part of a hygiene row.
pub fn stable(reason: &Reason) -> Vec<Stable> {
    match reason {
        Reason::Unsupported(part) => vec![unsupported(part)],
        Reason::TooManyRows(table) => vec![Stable::of("too_many_rows", *table)],
        Reason::MissingInput(input) => vec![Stable::of("reply_refused", input_code(*input))],
        Reason::Incomplete(found) => vec![incomplete(found)],
        Reason::NoSubjects => vec![Stable::of("no_receipt", "no_subjects")],
        Reason::UncitedChild(child) => {
            vec![Stable::of("no_receipt", format!("uncited_child: {child}"))]
        }
        Reason::Refused(refusal) => vec![Stable::of("refused_settings", refusal_code(refusal))],
        Reason::NotComplete(cause) => cause_entries(cause),
        Reason::Interface(hold) => vec![Stable::of("interface_gap", hold.gap().to_string())],
        Reason::Hygiene(found) => hygiene(found),
        Reason::Uml(gap) => vec![Stable::of("uml_target", uml_code(gap))],
    }
}

/// A hygiene row has the kind `hygiene.<code>`, the contract file as subject and each part as a
/// reason. The pointer of the entry in the contract is not in the key. A row without parts has
/// one entry that names its code only.
fn hygiene(found: &Hygiene) -> Vec<Stable> {
    let (place, parts) = found.parts();
    let kind = format!("hygiene.{}", found.code());
    let entry = |part: &str| Stable {
        kind: kind.clone(),
        subject: (!place.is_empty()).then(|| place.to_owned()),
        reason: part.to_owned(),
        count: 1,
    };
    if parts.is_empty() {
        vec![entry("")]
    } else {
        parts.iter().map(|part| entry(part)).collect()
    }
}

fn unsupported_kind(part: &Unsupported) -> &'static str {
    match part {
        Unsupported::ScopeProof(_) => "scope_proof",
        Unsupported::Rule(_) => "rule_kind_not_ported",
        Unsupported::InsideTree => "inside_contract_missing",
        Unsupported::Section(_) | Unsupported::Report | Unsupported::Baseline => "other",
        Unsupported::InsideRule => "inside_rule",
        Unsupported::TreeScope => "tree_scope",
        Unsupported::NoRules => "no_decided_rule",
        Unsupported::Hygiene(_) => "contract_hygiene_not_ported",
        Unsupported::HygieneInput => "contract_hygiene_not_read",
    }
}

fn unsupported(part: &Unsupported) -> Stable {
    let kind = unsupported_kind(part);
    match part {
        Unsupported::ScopeProof(part) => Stable::of(kind, part_code(part)),
        Unsupported::Section(section) => Stable::of("section", section.name()),
        Unsupported::Rule(rule) => Stable::of(kind, format!("{rule:?}")),
        Unsupported::Hygiene(codes) => Stable::of(kind, *codes),
        Unsupported::Report => Stable::of("report", "report"),
        Unsupported::Baseline => Stable::of("baseline", "baseline"),
        Unsupported::InsideTree
        | Unsupported::InsideRule
        | Unsupported::TreeScope
        | Unsupported::NoRules
        | Unsupported::HygieneInput => Stable::of(kind, kind),
    }
}

/// The code of a part of the scope proof, and the value that names it, if it has one.
fn part_code(part: &Part) -> String {
    let (code, value) = match part {
        Part::RuntimeRequirement => plain("runtime_requirement"),
        Part::ProfileLimit(subject) => ("profile_limit", Some(subject.as_str())),
        Part::ConstructSubjects(rule) => ("construct_subjects", Some(rule.as_str())),
        Part::ForeignRule => plain("foreign_rule"),
        Part::MountedTree => plain("mounted_tree"),
        Part::ScanRoots => plain("scan_roots"),
        Part::ScopedRequires => plain("scoped_requires"),
        Part::ContractSource => plain("contract_source"),
        Part::ScanLayout => plain("scan_layout"),
        Part::ReceiptSources => plain("receipt_sources"),
        Part::MountedLayerOrder => plain("mounted_layer_order"),
        Part::MountParent(parent) => ("mount_parent", Some(parent.as_str())),
    };
    coded(code, value)
}

/// A code that no value names.
fn plain(code: &str) -> (&str, Option<&str>) {
    (code, None)
}

fn input_code(input: Input) -> &'static str {
    match input {
        Input::Contract => "contract",
        Input::Reply => "reply",
        Input::Settings => "settings",
    }
}

/// The count of coverage gaps is the number of the collector entries, which the baseline keys
/// one by one, so it is not in this key. The count of unresolved imports that no gap names has
/// no other entry: it is the multiplicity.
fn incomplete(found: &Incomplete) -> Stable {
    match found {
        Incomplete::NoSourceFiles => Stable::of("incomplete_scope", "no_source_files"),
        Incomplete::CoverageGaps { .. } => Stable::of("incomplete_scope", "coverage_gaps"),
        Incomplete::UnknownImports(count) => {
            Stable::of("incomplete_scope", "unknown_imports").many(*count)
        }
    }
}

fn refusal_code(refusal: &Refusal) -> String {
    match refusal {
        Refusal::ProfileMismatch => "profile_mismatch".to_owned(),
        Refusal::OutsideNamespace(module) => format!("outside_namespace: {module}"),
        Refusal::StandardLibrary(rule) => format!("standard_library: {rule}"),
        Refusal::ScanRoots => "scan_roots".to_owned(),
    }
}

fn held(kind: &str, held: &Held) -> Vec<Stable> {
    held.pairs()
        .iter()
        .map(|(source, target)| Stable::of(kind, format!("{source} -> {target}")))
        .collect()
}

fn cause_entries(cause: &Cause) -> Vec<Stable> {
    let (code, value) = match cause {
        Cause::PairGaps(pairs) => return held("pair_gap", pairs),
        Cause::AllowedPairGaps(pairs) => return held("allowed_pair_gap", pairs),
        // AD-564: one entry for each doubt. The id of a gap moves with its line, so it is no key.
        Cause::ScopedGaps(scoped) => {
            let doubts = scoped.doubts().iter();
            return doubts.map(|d| Stable::of("gap_effect", d.word())).collect();
        }
        Cause::Undecided(count) => {
            return vec![Stable::of("undecided_imports", "undecided_imports").many(*count)]
        }
        Cause::WorkTree => ("work_tree", None),
        Cause::Runtime => ("runtime", None),
        Cause::Producer => ("producer", None),
        Cause::DynamicImport => ("dynamic_import", None),
        Cause::DependencyScopeUnproven => ("dependency_scope_unproven", None),
        Cause::ProfileLimit(subject) => ("profile_limit", Some(subject.as_str())),
        Cause::LayerMetadata(rule) => ("layer_metadata", Some(rule.as_str())),
        Cause::NoRuleSubjects(rule) => ("no_rule_subjects", Some(rule.as_str())),
        Cause::Receipt(why) => ("receipt", Some(*why)),
        Cause::InsideSourceDomain(parent) => ("inside_source_domain", Some(parent.as_str())),
        Cause::OutsideNamespace(reference) => ("outside_namespace", Some(reference.as_str())),
        Cause::OwnedFileOwner(path) => ("owned_file_owner", Some(path.as_str())),
        Cause::ClassSite(site) => ("class_site", Some(site.as_str())),
    };
    vec![Stable::of("incomplete_scope", coded(code, value))]
}

/// A code, with the value that names it when it has one: `code: value`.
fn coded(code: &str, value: Option<&str>) -> String {
    value.map_or_else(|| code.to_owned(), |value| format!("{code}: {value}"))
}

/// The counts of the declared UML intent are sizes of the contract, not causes, so they are not
/// in the key.
fn uml_code(gap: &UmlGap) -> String {
    match gap {
        UmlGap::Empty => "empty".to_owned(),
        UmlGap::NotCompared { .. } => "not_compared".to_owned(),
        UmlGap::Nested(_) => "nested".to_owned(),
        UmlGap::NothingCompared => "nothing_compared".to_owned(),
        UmlGap::Undecided { kinds, .. } => format!("undecided: {}", kinds.join(", ")),
        UmlGap::Incomplete(_) => "incomplete".to_owned(),
    }
}

#[cfg(test)]
#[path = "reason_key_tests.rs"]
mod tests;
