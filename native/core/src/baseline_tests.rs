// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// The two-way compare of a run with a baseline (AD-546). Each test names the difference that it
// plants. A mutation of one condition of `compare` must fail at least one of them.

use std::collections::BTreeMap;

use archkeel_contract::policy::parse_baseline;
use serde_json::{json, Value};

use super::{compare, Budgets, Observed, Violation};
use crate::gap_key::{Gaps, Key};

fn file(
    unknowns: Value,
    violations: Value,
    budgets: Value,
) -> archkeel_contract::policy::ValidationBaseline {
    let document = json!({
        "schema_version": "1.4.0", "violations": violations, "budgets": budgets,
        "unknowns": unknowns,
    });
    parse_baseline(document.to_string().as_bytes()).expect("a checked baseline")
}

fn older(budgets: Value) -> archkeel_contract::policy::ValidationBaseline {
    let document = json!({"schema_version": "1.3.0", "violations": [], "budgets": budgets});
    parse_baseline(document.to_string().as_bytes()).expect("a checked baseline")
}

fn entry(kind: &str, subject: &str, reason: &str, count: u64) -> Value {
    let mut value = json!({"kind": kind, "subject": subject, "reason": reason});
    if count > 1 {
        value["count"] = json!(count);
    }
    value
}

fn run(keys: &[(&str, &str, &str, u64)]) -> Observed {
    let keys: BTreeMap<Key, u64> = keys
        .iter()
        .map(|(kind, subject, reason, count)| {
            let key = Key {
                kind: (*kind).to_owned(),
                subject: (*subject).to_owned(),
                reason: (*reason).to_owned(),
            };
            (key, *count)
        })
        .collect();
    Observed {
        unknown_status: !keys.is_empty(),
        gaps: Gaps {
            keys,
            ..Gaps::default()
        },
        ..Observed::default()
    }
}

fn accepted() -> Value {
    json!([
        entry(
            "source_resolution_gap",
            "pkg.a",
            "dynamic_import: pickle",
            2
        ),
        entry("source_resolution_gap", "pkg.b", "dynamic_import: eval", 1),
    ])
}

fn same() -> Observed {
    run(&[
        (
            "source_resolution_gap",
            "pkg.a",
            "dynamic_import: pickle",
            2,
        ),
        ("source_resolution_gap", "pkg.b", "dynamic_import: eval", 1),
    ])
}

#[test]
fn every_unknown_accepted_is_current_and_exits_2_never_0() {
    let found = compare(&file(accepted(), json!([]), json!({})), &same());
    assert_eq!(
        (found.state.word(), found.state.exit_code()),
        ("current", 2)
    );
    assert_eq!(found.accepted_unknowns, 3);
    assert!(found.new.is_empty() && found.gone.is_empty());
}

#[test]
fn a_run_with_no_unknown_and_no_difference_exits_0() {
    let found = compare(&file(json!([]), json!([]), json!({})), &run(&[]));
    assert_eq!(
        (found.state.word(), found.state.exit_code()),
        ("current", 0)
    );
}

#[test]
fn a_new_gap_that_is_not_accepted_is_red() {
    let mut now = same();
    let key = Key {
        kind: "source_resolution_gap".into(),
        subject: "pkg.c".into(),
        reason: "dynamic_import: exec".into(),
    };
    now.gaps.keys.insert(key, 1);
    let found = compare(&file(accepted(), json!([]), json!({})), &now);
    assert_eq!((found.state.word(), found.state.exit_code()), ("drift", 1));
    assert_eq!(found.new.len(), 1);
    assert_eq!(found.new[0].subject, "pkg.c");
    assert!(found.gone.is_empty());
}

#[test]
fn an_accepted_gap_that_vanished_is_stale_and_red() {
    let now = run(&[(
        "source_resolution_gap",
        "pkg.a",
        "dynamic_import: pickle",
        2,
    )]);
    let found = compare(&file(accepted(), json!([]), json!({})), &now);
    assert_eq!((found.state.word(), found.state.exit_code()), ("drift", 1));
    assert_eq!(found.gone.len(), 1);
    assert_eq!((found.gone[0].run, found.gone[0].file), (0, 1));
}

#[test]
fn a_changed_reason_is_one_new_and_one_stale_entry() {
    let now = run(&[
        (
            "source_resolution_gap",
            "pkg.a",
            "dynamic_import: pickle",
            2,
        ),
        ("source_resolution_gap", "pkg.b", "dynamic_import: exec", 1),
    ]);
    let found = compare(&file(accepted(), json!([]), json!({})), &now);
    assert_eq!(found.state.exit_code(), 1);
    assert_eq!((found.new.len(), found.gone.len()), (1, 1));
    assert_eq!(found.new[0].reason, "dynamic_import: exec");
    assert_eq!(found.gone[0].reason, "dynamic_import: eval");
}

#[test]
fn a_higher_count_is_new_and_a_lower_count_is_stale() {
    let up = run(&[
        (
            "source_resolution_gap",
            "pkg.a",
            "dynamic_import: pickle",
            3,
        ),
        ("source_resolution_gap", "pkg.b", "dynamic_import: eval", 1),
    ]);
    let found = compare(&file(accepted(), json!([]), json!({})), &up);
    assert_eq!((found.state.word(), found.state.exit_code()), ("drift", 1));
    assert_eq!((found.new[0].run, found.new[0].file), (3, 2));
    let down = run(&[
        (
            "source_resolution_gap",
            "pkg.a",
            "dynamic_import: pickle",
            1,
        ),
        ("source_resolution_gap", "pkg.b", "dynamic_import: eval", 1),
    ]);
    let found = compare(&file(accepted(), json!([]), json!({})), &down);
    assert_eq!((found.state.word(), found.state.exit_code()), ("drift", 1));
    assert_eq!((found.gone[0].run, found.gone[0].file), (1, 2));
}

#[test]
fn one_acceptance_never_covers_two_gaps_of_one_key() {
    // Two sites of one key: the file accepts one, so the second site is new.
    let one = file(json!([entry("k", "s", "r", 1)]), json!([]), json!({}));
    let found = compare(&one, &run(&[("k", "s", "r", 2)]));
    assert_eq!((found.state.word(), found.state.exit_code()), ("drift", 1));
    assert_eq!(found.accepted_unknowns, 1);
    // Another key does not borrow the acceptance of its neighbour.
    let found = compare(&one, &run(&[("k", "s", "r", 1), ("k", "t", "r", 1)]));
    assert_eq!(found.new[0].subject, "t");
}

#[test]
fn a_violation_that_the_file_lacks_is_red_with_an_accepted_unknown() {
    let mut now = same();
    let item = Violation {
        rules: vec!["R".into()],
        subjects: vec!["a".into(), "b".into()],
        roles: vec![("a".into(), "b".into())],
    };
    now.violations.insert(item, 1);
    let found = compare(&file(accepted(), json!([]), json!({})), &now);
    assert_eq!((found.state.word(), found.state.exit_code()), ("drift", 1));
    assert_eq!(found.new[0].what, "violation");
}

#[test]
fn an_accepted_violation_keeps_exit_0_without_unknown_and_a_stale_one_is_red() {
    let debt = json!([{"rules": ["R"], "subjects": ["a", "b"], "count": 2,
        "roles": [{"source": "a", "target": "b"}]}]);
    let mut now = run(&[]);
    now.violations.insert(
        Violation {
            rules: vec!["R".into()],
            subjects: vec!["a".into(), "b".into()],
            roles: vec![("a".into(), "b".into())],
        },
        2,
    );
    let found = compare(&file(json!([]), debt.clone(), json!({})), &now);
    assert_eq!(
        (found.state.word(), found.state.exit_code()),
        ("current", 0)
    );
    let found = compare(&file(json!([]), debt.clone(), json!({})), &run(&[]));
    assert_eq!((found.state.word(), found.state.exit_code()), ("drift", 1));
    assert_eq!(found.gone[0].what, "violation");
    // One fewer: stale. One more: new.
    *now.violations.values_mut().next().unwrap() = 1;
    assert_eq!(
        compare(&file(json!([]), debt.clone(), json!({})), &now)
            .state
            .exit_code(),
        1
    );
    *now.violations.values_mut().next().unwrap() = 3;
    assert_eq!(
        compare(&file(json!([]), debt, json!({})), &now)
            .state
            .exit_code(),
        1
    );
}

#[test]
fn a_violation_in_the_other_direction_is_not_the_accepted_one() {
    let debt = json!([{"rules": ["R"], "subjects": ["a", "b"], "count": 1,
        "roles": [{"source": "a", "target": "b"}]}]);
    let mut now = run(&[]);
    now.violations.insert(
        Violation {
            rules: vec!["R".into()],
            subjects: vec!["a".into(), "b".into()],
            roles: vec![("b".into(), "a".into())],
        },
        1,
    );
    let found = compare(&file(json!([]), debt, json!({})), &now);
    assert_eq!((found.state.word(), found.state.exit_code()), ("drift", 1));
    assert_eq!(found.new[0].reason, "direction differs");
}

#[test]
fn a_budget_above_the_file_is_red_and_below_is_stale() {
    let budgets = json!({"cycle_edges": 2, "private_crossings": 0});
    let at = |cycles, crossings| Observed {
        budgets: Budgets {
            cycle_edges: Some(cycles),
            private_crossings: Some(crossings),
        },
        ..Observed::default()
    };
    let base = file(json!([]), json!([]), budgets);
    assert_eq!(compare(&base, &at(2, 0)).state.exit_code(), 0);
    let above = compare(&base, &at(3, 0));
    assert_eq!(
        (
            above.state.word(),
            above.state.exit_code(),
            above.new[0].reason.as_str()
        ),
        ("drift", 1, "above the baseline")
    );
    let below = compare(&base, &at(1, 0));
    assert_eq!(
        (
            below.state.word(),
            below.state.exit_code(),
            below.gone[0].reason.as_str()
        ),
        ("drift", 1, "below the baseline")
    );
    assert_eq!(
        compare(&base, &at(2, 1)).new[0].subject,
        "private_crossings"
    );
}

#[test]
fn a_budget_that_the_run_does_not_measure_is_a_named_gap_with_exit_2() {
    let base = file(json!([]), json!([]), json!({"cycle_edges": 2}));
    let found = compare(&base, &Observed::default());
    assert_eq!(
        (found.state.word(), found.state.exit_code()),
        ("current", 2)
    );
    assert_eq!(found.gaps[0].kind, "budget.unmeasured");
}

#[test]
fn a_budget_that_this_core_cannot_measure_is_never_read_as_zero_or_held() {
    for name in [
        "calls_unresolved",
        "typing_positions",
        "untyped_private_accesses",
    ] {
        let base = file(json!([]), json!([]), json!({ name: 0 }));
        let found = compare(&base, &Observed::default());
        assert_eq!(
            (found.state.word(), found.state.exit_code()),
            ("current", 2),
            "{name}"
        );
        assert_eq!(found.gaps[0].kind, "budget.unmeasured");
    }
}

#[test]
fn an_older_schema_names_the_budgets_of_another_analyzer_and_compares_the_rest() {
    let base = older(
        json!({"calls_unresolved": 1429, "typing_positions": 178, "cycle_edges": 2,
        "private_crossings": 0, "untyped_private_accesses": 0}),
    );
    let mut now = run(&[("k", "s", "r", 1)]);
    now.budgets = Budgets {
        cycle_edges: Some(2),
        private_crossings: Some(0),
    };
    let found = compare(&base, &now);
    // The UNKNOWN compare is off: the new key is not red. Three named gaps hold exit 2.
    assert_eq!(
        (found.state.word(), found.state.exit_code()),
        ("current", 2)
    );
    assert!(found.new.is_empty());
    assert_eq!(found.gaps.len(), 3);
    assert!(found
        .gaps
        .iter()
        .all(|gap| gap.kind == "baseline.budget_of_older_schema"));
    now.budgets.cycle_edges = Some(3);
    assert_eq!(compare(&base, &now).state.exit_code(), 1);
}

#[test]
fn an_older_file_gives_exit_2_for_an_unknown_and_0_for_none() {
    let base = older(json!({}));
    assert_eq!(compare(&base, &same()).state.exit_code(), 2);
    assert_eq!(compare(&base, &run(&[])).state.exit_code(), 0);
}

#[test]
fn a_refused_part_is_never_accepted_and_exits_1_so_that_exit_2_means_all_accepted() {
    let mut now = run(&[]);
    now.gaps.unacceptable.push("reply: refused".to_owned());
    now.unknown_status = true;
    let found = compare(&file(json!([]), json!([]), json!({})), &now);
    assert_eq!(
        (found.state.word(), found.state.exit_code()),
        ("not_compared", 1)
    );
    assert_eq!(found.gaps[0].kind, "baseline.not_compared");
}

#[test]
fn an_unknown_status_without_a_key_still_exits_2() {
    let mut now = run(&[]);
    now.unknown_status = true;
    let found = compare(&file(json!([]), json!([]), json!({})), &now);
    assert_eq!(
        (found.state.word(), found.state.exit_code()),
        ("current", 2)
    );
}

#[test]
fn a_rule_row_is_accepted_only_when_every_key_of_the_row_is_accepted() {
    let key = |subject: &str| Key {
        kind: "k".into(),
        subject: subject.into(),
        reason: "r".into(),
    };
    let mut now = run(&[("k", "a", "r", 1), ("k", "b", "r", 1)]);
    now.gaps.by_rule.insert("ONE".into(), vec![key("a")]);
    now.gaps
        .by_rule
        .insert("TWO".into(), vec![key("a"), key("b")]);
    let base = file(json!([entry("k", "a", "r", 1)]), json!([]), json!({}));
    let found = compare(&base, &now);
    assert_eq!(found.accepted_rules, vec!["ONE".to_owned()]);
    assert_eq!((found.accepted_entries, found.accepted_unknowns), (1, 1));
    // A count above the file is not accepted: the second site is new.
    let mut more = run(&[("k", "a", "r", 2)]);
    more.gaps.by_rule.insert("ONE".into(), vec![key("a")]);
    assert!(compare(&base, &more).accepted_rules.is_empty());
}

#[test]
fn entries_and_items_are_counted_apart() {
    let base = file(
        json!([entry("k", "a", "r", 3), entry("k", "b", "r", 1)]),
        json!([]),
        json!({}),
    );
    let found = compare(&base, &run(&[("k", "a", "r", 3), ("k", "b", "r", 1)]));
    assert_eq!((found.accepted_entries, found.accepted_unknowns), (2, 4));
}
