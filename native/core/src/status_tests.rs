// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

use std::collections::BTreeMap;

use super::{status, unexplained, DECLARATION, FAIL, PASS, UNKNOWN};
use crate::rules::RuleAnswer;

fn answer(rows: &[(&str, &str, usize, &str)]) -> RuleAnswer {
    let mut answer = RuleAnswer::default();
    for (rule, word, violations, reason) in rows {
        let kind = "complete_assignment".to_owned();
        answer
            .decided
            .insert((*rule).to_owned(), [kind, (*word).to_owned()]);
        if *violations > 0 {
            answer.violations.insert((*rule).to_owned(), *violations);
        }
        if !reason.is_empty() {
            answer
                .explained
                .insert((*rule).to_owned(), (*reason).to_owned());
        }
    }
    answer
}

#[test]
fn the_status_follows_from_the_rows() {
    let pass = answer(&[("A", PASS, 0, ""), ("B", PASS, 0, "")]);
    assert_eq!(status(&pass.decided, false, true), PASS);
    assert_eq!(status(&pass.decided, true, true), UNKNOWN);
    // L-35b: PASS needs the complete scope of the run, also when each rule passes.
    assert_eq!(status(&pass.decided, false, false), UNKNOWN);
    let unknown = answer(&[("A", PASS, 0, ""), ("B", UNKNOWN, 0, "why")]);
    assert_eq!(status(&unknown.decided, false, true), UNKNOWN);
    let fail = answer(&[("A", FAIL, 1, ""), ("B", UNKNOWN, 0, "why")]);
    assert_eq!(status(&fail.decided, true, false), FAIL);
    // Zero decided rules: PASS only with a complete scope and nothing named.
    assert_eq!(status(&BTreeMap::new(), false, true), PASS);
    assert_eq!(status(&BTreeMap::new(), false, false), UNKNOWN);
    assert_eq!(status(&BTreeMap::new(), true, true), UNKNOWN);
    // A permission declaration has no verdict and holds back no PASS (`inspect_observation`).
    let declared = answer(&[("A", PASS, 0, ""), ("B", DECLARATION, 0, "")]);
    assert_eq!(status(&declared.decided, false, true), PASS);
    assert_eq!(unexplained(&declared), None);
    assert!(unexplained(&answer(&[("B", DECLARATION, 1, "")])).is_some());
    assert!(unexplained(&answer(&[("B", DECLARATION, 0, "why")])).is_some());
}

#[test]
fn each_status_other_than_pass_has_its_explaining_row() {
    assert_eq!(unexplained(&answer(&[("A", FAIL, 2, "")])), None);
    assert_eq!(unexplained(&answer(&[("A", UNKNOWN, 0, "why")])), None);
    assert_eq!(unexplained(&answer(&[("A", PASS, 0, "")])), None);
    // L-23: a FAIL rule without a violation row is an inconsistent frame.
    let bad = [
        ("A", FAIL, 0, ""),
        ("A", UNKNOWN, 0, ""),
        ("A", PASS, 1, ""),
        ("A", PASS, 0, "why"),
        ("A", UNKNOWN, 1, "why"),
        ("A", "OTHER", 0, ""),
    ];
    for row in bad {
        assert!(unexplained(&answer(&[row])).is_some(), "{row:?}");
    }
    let mut orphan = answer(&[("A", PASS, 0, "")]);
    orphan.violations.insert("B".to_owned(), 1);
    assert!(unexplained(&orphan).is_some());
}
