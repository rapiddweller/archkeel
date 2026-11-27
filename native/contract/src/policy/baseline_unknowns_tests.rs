// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The accepted UNKNOWN list of schema 1.4.0 (AD-546).

use serde_json::{json, Value};

use crate::policy::{
    baseline_bytes, parse_baseline, AcceptedUnknown, BaselineBudget, BaselineError,
    ValidationBaseline,
};

fn entry(kind: &str, subject: &str, reason: &str) -> Value {
    json!({"kind": kind, "subject": subject, "reason": reason})
}

fn document(unknowns: Value) -> Value {
    json!({"schema_version": "1.4.0", "violations": [], "budgets": {}, "unknowns": unknowns})
}

fn parse(value: &Value) -> Result<ValidationBaseline, BaselineError> {
    parse_baseline(&serde_json::to_vec(value).unwrap())
}

fn error(value: &Value) -> String {
    parse(value).unwrap_err().to_string()
}

#[test]
fn a_sorted_list_with_counts_reads_and_writes_the_same_bytes() {
    let mut counted = entry("b", "s", "r");
    counted["count"] = json!(3);
    let value = document(json!([entry("a", "s", "r"), counted]));
    let baseline = parse(&value).unwrap();
    let list = baseline.unknowns().as_ref().unwrap();
    assert_eq!((*list[0].count(), *list[1].count()), (1, 3));
    let bytes = baseline_bytes(&baseline);
    let text = String::from_utf8(bytes.clone()).unwrap();
    assert!(text.contains("\"schema_version\": \"1.4.0\""));
    assert_eq!(
        text.matches("\"count\"").count(),
        1,
        "a count of 1 is not written"
    );
    assert_eq!(baseline_bytes(&parse_baseline(&bytes).unwrap()), bytes);
}

#[test]
fn a_count_of_one_is_read_and_written_without_the_field() {
    let mut one = entry("a", "s", "r");
    one["count"] = json!(1);
    let baseline = parse(&document(json!([one]))).unwrap();
    assert_eq!(*baseline.unknowns().as_ref().unwrap()[0].count(), 1);
    assert!(!String::from_utf8(baseline_bytes(&baseline))
        .unwrap()
        .contains("\"count\""));
}

#[test]
fn an_empty_list_is_a_baseline_that_accepts_nothing_and_an_older_file_has_no_list() {
    let baseline = parse(&document(json!([]))).unwrap();
    assert_eq!(baseline.unknowns().as_ref().map(Vec::len), Some(0));
    let older = json!({"schema_version": "1.3.0", "violations": [], "budgets": {}});
    assert!(parse(&older).unwrap().unknowns().is_none());
}

#[test]
fn a_duplicate_an_unsorted_entry_an_unknown_field_and_a_count_of_zero_are_refused() {
    let repeated = document(json!([entry("a", "s", "r"), entry("a", "s", "r")]));
    assert_eq!(
        error(&repeated),
        "baseline.unknowns[1] repeats an earlier entry, a | s | r; give it one count instead"
    );
    let unsorted = document(json!([entry("b", "s", "r"), entry("a", "s", "r")]));
    assert_eq!(
        error(&unsorted),
        "baseline.unknowns[1], a | s | r, is not sorted by kind, subject and reason"
    );
    let mut extra = entry("a", "s", "r");
    extra["line"] = json!(4);
    assert_eq!(
        error(&document(json!([extra]))),
        "baseline.unknowns[0] fields mismatch"
    );
    let mut zero = entry("a", "s", "r");
    zero["count"] = json!(0);
    assert_eq!(
        error(&document(json!([zero]))),
        "baseline.unknowns[0].count must be at least 1"
    );
    let mut text = entry("a", "s", "r");
    text["count"] = json!("2");
    assert_eq!(
        error(&document(json!([text]))),
        "baseline.unknowns[0].count must be a non-negative integer"
    );
    assert_eq!(
        error(&document(json!({}))),
        "baseline.unknowns must be an array"
    );
}

#[test]
fn the_order_is_by_kind_then_subject_then_reason() {
    let sorted = document(json!([entry("a", "z", "z"), entry("b", "a", "a")]));
    assert!(parse(&sorted).is_ok());
    let by_subject = document(json!([entry("a", "b", "a"), entry("a", "a", "z")]));
    assert!(error(&by_subject).contains("is not sorted"));
    let by_reason = document(json!([entry("a", "a", "b"), entry("a", "a", "a")]));
    assert!(error(&by_reason).contains("is not sorted"));
}

#[test]
fn a_file_of_1_4_0_needs_the_list_and_an_older_file_must_not_have_it() {
    let mut value = document(json!([]));
    value.as_object_mut().unwrap().remove("unknowns");
    assert_eq!(error(&value), "baseline fields mismatch");
    let mut older = document(json!([]));
    older["schema_version"] = json!("1.3.0");
    assert_eq!(error(&older), "baseline fields mismatch");
}

#[test]
fn a_run_baseline_is_sorted_and_has_no_zero_count() {
    let make = |kind: &str| AcceptedUnknown::new(kind.into(), "s".into(), "r".into(), 2).unwrap();
    let baseline = ValidationBaseline::of_run(
        Vec::new(),
        vec![BaselineBudget::Scalar {
            name: crate::BudgetName::CycleEdges,
            value: 2,
        }],
        vec![make("b"), make("a")],
    );
    let text = String::from_utf8(baseline_bytes(&baseline)).unwrap();
    assert!(text.find("\"a\"").unwrap() < text.find("\"b\"").unwrap());
    assert!(AcceptedUnknown::new("a".into(), "s".into(), "r".into(), 0).is_err());
    assert_eq!(parse_baseline(text.as_bytes()).unwrap(), baseline);
}

#[test]
fn schema_1_5_0_names_every_cause_and_a_run_writes_it_while_1_4_0_keeps_its_form() {
    // AD-1330: a file of 1.4.0 names the first cause of a rule only; a file of 1.5.0 names them all.
    let mut value = document(json!([entry("a", "s", "r")]));
    let legacy = parse(&value).unwrap();
    assert!(!legacy.all_causes());
    assert!(String::from_utf8(baseline_bytes(&legacy))
        .unwrap()
        .contains("\"schema_version\": \"1.4.0\""));
    value["schema_version"] = json!("1.5.0");
    let current = parse(&value).unwrap();
    assert!(*current.all_causes());
    assert!(String::from_utf8(baseline_bytes(&current))
        .unwrap()
        .contains("\"schema_version\": \"1.5.0\""));
    let run = ValidationBaseline::of_run(Vec::new(), Vec::new(), Vec::new());
    assert!(*run.all_causes());
}
