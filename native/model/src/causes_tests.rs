// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The words of a cause that holds a rule through module pairs: a pair is counted as a pair, and
//! a cut list says how many pairs it shows.

use super::{Cause, Held};

fn pairs(count: usize) -> Vec<(String, String)> {
    (0..count)
        .map(|n| (format!("s{n}"), format!("t{n}")))
        .collect()
}

fn text(count: usize) -> String {
    let all = pairs(count);
    let held = Held::of(all.iter().map(|(s, t)| (s.as_str(), t.as_str()))).expect("a pair");
    Cause::PairGaps(held).to_string()
}

#[test]
fn a_cut_list_names_its_unit_and_how_many_pairs_it_shows() {
    assert_eq!(
        text(8),
        "8 module pairs with gaps that the contract does not allow (showing 5): \
         s0 -> t0, s1 -> t1, s2 -> t2, s3 -> t3, s4 -> t4 and 3 more pairs"
    );
}

#[test]
fn a_complete_list_has_no_showing_note() {
    assert_eq!(
        text(2),
        "2 module pairs with gaps that the contract does not allow: s0 -> t0, s1 -> t1"
    );
    assert_eq!(
        text(1),
        "1 module pair with gaps that the contract does not allow: s0 -> t0"
    );
    assert!(!text(5).contains("showing"));
}

#[test]
fn no_pair_gives_no_cause() {
    assert!(Held::of(std::iter::empty()).is_none());
}

#[test]
fn a_dropped_gap_cause_uses_the_same_unit() {
    let all = pairs(1);
    let held = Held::of(all.iter().map(|(s, t)| (s.as_str(), t.as_str()))).expect("a pair");
    assert_eq!(
        Cause::AllowedPairGaps(held).to_string(),
        "1 module pair with gaps that the contract allows and that can change the rule: s0 -> t0"
    );
}

#[test]
fn two_records_of_one_pair_are_one_pair_and_two_records() {
    let held = Held::of([("a", "b"), ("a", "b")].into_iter()).expect("a pair");
    assert_eq!((held.count(), held.records), (1, 2));
    assert_eq!(
        Cause::PairGaps(held).to_string(),
        "1 module pair with gaps that the contract does not allow (from 2 gap records): a -> b"
    );
}

#[test]
fn a_cut_list_shows_distinct_pairs_and_counts_them_not_the_records() {
    let records: Vec<(String, String)> = (0..7)
        .flat_map(|n| std::iter::repeat_n((format!("s{n}"), format!("t{n}")), 2))
        .collect();
    let held = Held::of(records.iter().map(|(s, t)| (s.as_str(), t.as_str()))).expect("a pair");
    assert_eq!((held.count(), held.records, held.shown().len()), (7, 14, 5));
    assert!(Cause::PairGaps(held).to_string().starts_with(
        "7 module pairs with gaps that the contract does not allow (from 14 gap records) \
         (showing 5): s0 -> t0, s1 -> t1, s2 -> t2, s3 -> t3, s4 -> t4 and 2 more pairs"
    ));
}
