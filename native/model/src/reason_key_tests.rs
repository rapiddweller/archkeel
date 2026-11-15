// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// The stable key of a reason (AD-546): it holds no count of other entries, no pointer and no text
// that moves with an unrelated edit.

use archkeel_contract::RuleKind;

use crate::causes::{Cause, Held, Part};
use crate::coverage::Incomplete;
use crate::reason::{Hygiene, Reason, Unsupported};
use crate::reason_key::{gap_kind, stable};

fn held(pairs: &[(&str, &str)]) -> Held {
    Held::of(pairs.iter().copied()).expect("a gap")
}

#[test]
fn the_count_of_coverage_gaps_is_not_in_the_key() {
    let one = stable(&Reason::Incomplete(Incomplete::CoverageGaps(1)));
    let many = stable(&Reason::Incomplete(Incomplete::CoverageGaps(157)));
    assert_eq!(one, many);
    assert_eq!(one[0].count, 1);
}

#[test]
fn the_count_of_imports_that_no_gap_names_is_the_multiplicity() {
    let found = stable(&Reason::Incomplete(Incomplete::UnknownImports(3)));
    assert_eq!(found.len(), 1);
    assert_eq!(found[0].count, 3);
    let undecided = stable(&Reason::NotComplete(Cause::Undecided(5)));
    assert_eq!(undecided[0].count, 5);
    assert_eq!(undecided[0].kind, "undecided_imports");
}

#[test]
fn each_pair_of_a_pair_gap_is_one_entry_and_a_swap_changes_the_key() {
    let first = stable(&Reason::NotComplete(Cause::PairGaps(held(&[("a", "b"), ("c", "d")]))));
    assert_eq!(first.len(), 2);
    assert_eq!(first[0].reason, "a -> b");
    let swapped = stable(&Reason::NotComplete(Cause::PairGaps(held(&[("a", "b"), ("c", "e")]))));
    assert_ne!(first, swapped);
    let more = Reason::NotComplete(Cause::PairGaps(held(&[("a", "b"), ("c", "d"), ("e", "f")])));
    assert_eq!(stable(&more).len(), 3);
}

#[test]
fn a_scope_proof_part_and_a_rule_kind_have_their_own_code() {
    let part = stable(&Reason::Unsupported(Unsupported::ScopeProof(Part::ScopedRequires)));
    assert_eq!((part[0].kind.as_str(), part[0].reason.as_str()), ("scope_proof", "scoped_requires"));
    let rule = stable(&Reason::Unsupported(Unsupported::Rule(RuleKind::BoundaryTypes)));
    assert_eq!(rule[0].kind, "rule_kind_not_ported");
    assert_eq!(rule[0].reason, "BoundaryTypes");
    assert_eq!(rule[0].subject, None);
}

#[test]
fn a_hygiene_row_has_the_file_as_subject_and_ignores_the_pointer_in_its_text() {
    let make = |pointer: &str| {
        let detail = format!("c.json{pointer} entry: claim 3");
        Reason::Hygiene(Hygiene::keyed("graph.drift", detail, "c.json", vec!["entry".to_owned()]))
    };
    assert_eq!(stable(&make("/components/1")), stable(&make("/components/9")));
    let found = stable(&make("/components/1"));
    assert_eq!(found[0].kind, "hygiene.graph.drift");
    assert_eq!(found[0].subject.as_deref(), Some("c.json"));
    assert_eq!(found[0].reason, "entry");
}

#[test]
fn the_shell_kinds_are_the_words_that_the_text_prefixes_gave() {
    let kind = |reason: Reason| gap_kind(&reason);
    assert_eq!(kind(Reason::Unsupported(Unsupported::ScopeProof(Part::ForeignRule))), "scope_proof");
    assert_eq!(kind(Reason::Unsupported(Unsupported::Rule(RuleKind::BoundaryTypes))), "rule_kind_not_ported");
    assert_eq!(kind(Reason::Unsupported(Unsupported::NoRules)), "no_decided_rule");
    assert_eq!(kind(Reason::Unsupported(Unsupported::Hygiene("a"))), "contract_hygiene_not_ported");
    assert_eq!(kind(Reason::Unsupported(Unsupported::HygieneInput)), "contract_hygiene_not_read");
    assert_eq!(kind(Reason::Hygiene(Hygiene::new("graph.drift", String::new()))), "graph.drift");
    assert_eq!(kind(Reason::NoSubjects), "other");
}
