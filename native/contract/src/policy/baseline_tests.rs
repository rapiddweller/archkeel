// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Baseline grammar and byte bounds (AD-386).

use serde_json::{json, Value};

use crate::policy::{baseline_bytes, parse_baseline, BaselineError, MAX_BASELINE_BYTES};

fn entry() -> Value {
    json!({"rules": ["B", "A", "A"], "subjects": ["z", "a", "z"], "count": 2})
}

fn document() -> Value {
    json!({"schema_version": "1.3.0", "violations": [entry()], "budgets": {}})
}

fn parse(value: &Value) -> Result<crate::policy::ValidationBaseline, BaselineError> {
    parse_baseline(&serde_json::to_vec(value).unwrap())
}

fn error(value: &Value) -> String {
    parse(value).unwrap_err().to_string()
}

#[test]
fn baseline_keeps_each_entry_and_repeated_fingerprint_members() {
    let baseline = parse(&document()).unwrap();
    let item = &baseline.violations()[0];
    assert_eq!(item.fingerprint().rules(), &["A", "A", "B"]);
    assert_eq!(item.fingerprint().subjects(), &["a", "z", "z"]);
    assert_eq!(*item.count(), 2);
    assert_eq!(
        parse_baseline(&baseline_bytes(&baseline)).unwrap(),
        baseline
    );
    let mut empty = document();
    empty["violations"] = json!([{"rules": [], "subjects": [""], "count": 1}]);
    assert!(parse(&empty).is_ok());
}

#[test]
fn baseline_reads_all_four_versions_and_writes_the_current_version() {
    for version in ["1.0.0", "1.1.0", "1.2.0", "1.3.0"] {
        let mut value = document();
        value["schema_version"] = json!(version);
        if version < "1.2.0" {
            value.as_object_mut().unwrap().remove("budgets");
        }
        let baseline = parse(&value).unwrap();
        assert!(String::from_utf8(baseline_bytes(&baseline))
            .unwrap()
            .contains("\"1.3.0\""));
    }
    assert_eq!(error(&json!([])), "baseline must be an object");
    assert_eq!(
        error(&json!({})),
        "baseline schema None cannot be read as 1.0.0, 1.1.0, 1.2.0, 1.3.0"
    );
    let mut value = document();
    value["schema_version"] = json!("1.3.1");
    assert_eq!(
        error(&value),
        "baseline schema '1.3.1' cannot be read as 1.0.0, 1.1.0, 1.2.0, 1.3.0"
    );
    value["schema_version"] = json!("1.3.0");
    value["extra"] = json!(1);
    assert_eq!(error(&value), "baseline fields mismatch");
    value.as_object_mut().unwrap().remove("budgets");
    assert_eq!(error(&value), "baseline fields mismatch");
}

#[test]
fn baseline_rejects_unknown_entry_fields_and_bad_counts() {
    for bad in [json!(true), json!(null), json!(1.0), json!(-1), json!("1")] {
        let mut value = document();
        value["violations"][0]["count"] = bad;
        assert_eq!(
            error(&value),
            "baseline.violations[0].count must be a non-negative integer"
        );
    }
    let mut value = document();
    value["violations"][0]["count"] = json!(0);
    assert_eq!(
        error(&value),
        "baseline.violations[0].count must be at least 1"
    );
    value["violations"][0]["extra"] = json!(0);
    assert_eq!(error(&value), "baseline.violations[0] fields mismatch");
    value["violations"] = json!({});
    assert_eq!(error(&value), "baseline.violations must be an array");
}

#[test]
fn baseline_rejects_duplicate_fingerprints_after_validating_all_entries() {
    let mut value = document();
    let mut second = entry();
    second["subjects"] = json!(["z", "z", "a"]);
    value["violations"] = json!([entry(), second]);
    assert_eq!(error(&value), "baseline.violations[1] repeats baseline.violations[0], A A B | a z z (subjects match in any order); give it one count instead");
    value["violations"]
        .as_array_mut()
        .unwrap()
        .push(json!(null));
    assert_eq!(error(&value), "baseline.violations[2] must be an object");
}

#[test]
fn baseline_validates_and_sorts_roles_without_changing_identity() {
    let mut value = document();
    value["violations"][0]["roles"] = json!([
        {"source": "z", "target": "a"}, {"source": "", "target": ""}
    ]);
    let baseline = parse(&value).unwrap();
    assert_eq!(baseline.violations()[0].roles()[0].source(), "");
    assert_eq!(
        parse_baseline(&baseline_bytes(&baseline)).unwrap(),
        baseline
    );
    value["schema_version"] = json!("1.0.0");
    value.as_object_mut().unwrap().remove("budgets");
    assert_eq!(error(&value), "baseline.violations[0] fields mismatch");
    value["schema_version"] = json!("1.1.0");
    value["violations"][0]["roles"] =
        json!([{"source": "a", "target": "b"}, {"source": "a", "target": "b"}]);
    assert_eq!(error(&value), "baseline.violations[0].roles repeats a role");
    value["violations"][0]["roles"] = json!([{"source": 1, "target": "b"}]);
    assert_eq!(
        error(&value),
        "baseline.violations[0].roles[0].source must be a string"
    );
    value["violations"][0]["roles"] = json!(null);
    assert_eq!(
        error(&value),
        "baseline.violations[0].roles must be an array"
    );
}

#[test]
fn baseline_validates_scalar_and_keyed_budgets() {
    let mut value = document();
    value["budgets"] = json!({"cycle_edges": 0, "facade_names": {" a ": ["", "a", "é"]}});
    let baseline = parse(&value).unwrap();
    assert_eq!(baseline.budgets().len(), 2);
    assert_eq!(
        parse_baseline(&baseline_bytes(&baseline)).unwrap(),
        baseline
    );
    value["budgets"]["facade_names"][" a "] = json!(["b", "a"]);
    assert_eq!(
        error(&value),
        "baseline.budgets.facade_names. a  must list sorted unique names"
    );
    value["budgets"] = json!({"facade_names": {"\u{1c}": []}});
    assert_eq!(
        error(&value),
        "baseline.budgets.facade_names must not be empty"
    );
    value["budgets"] = json!({"facade_names": {"": 1}});
    assert_eq!(
        error(&value),
        "baseline.budgets.facade_names. must be a string array"
    );
    value["budgets"] = json!({"facade_names": {}});
    value["schema_version"] = json!("1.2.0");
    assert_eq!(
        error(&value),
        "baseline.budgets.facade_names is not a supported measurement budget"
    );
    value["budgets"] = json!({"violations": 0});
    assert_eq!(
        error(&value),
        "baseline.budgets.violations is not a supported measurement budget"
    );
}

#[test]
fn baseline_bounds_and_hostile_json_are_named_refusals() {
    assert!(matches!(
        parse_baseline(&vec![b' '; MAX_BASELINE_BYTES + 1]),
        Err(BaselineError::TooLarge)
    ));
    for bytes in [
        b"".as_slice(),
        b"\xff",
        b"\xef\xbb\xbf{}",
        b"{}{}",
        b"NaN",
        br#""\ud800""#,
    ] {
        assert!(matches!(parse_baseline(bytes), Err(BaselineError::Json(_))));
    }
    assert!(matches!(
        parse_baseline(br#"{"x":1,"x":2}"#),
        Err(BaselineError::DuplicateKey(_))
    ));
    let deep = format!("{}{}", "[".repeat(10000), "]".repeat(10000));
    assert!(matches!(
        parse_baseline(deep.as_bytes()),
        Err(BaselineError::Json(_))
    ));
}
