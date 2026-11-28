// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// AD-1550: `resolved_elsewhere` separates the named doubt from the execution doubt of a call.

use crate::type_reach_facts::Facts;
use crate::type_reach_filter::Filter;
use std::collections::BTreeSet;

const TABLE: &str = r#"["crates/app/src/a.rs","crates/app/src/b.rs","crates/app/src/c.rs"]"#;
const B: &str = "crates/app/src/b.rs";
const AT: (&str, i64, i64) = ("crates/app/src/a.rs", 3, 9);

fn filter_of(calls: &[&str]) -> Filter<'static> {
    let mut facts = Facts::empty();
    let mut lines = vec![
        r#"{"k":"build","test":false}"#.to_owned(),
        format!("{{\"k\":\"str\",\"v\":{TABLE}}}"),
    ];
    lines.extend(calls.iter().map(|call| (*call).to_owned()));
    facts.absorb(&lines.join("\n")).unwrap();
    Filter::new(Box::leak(Box::new(vec![facts])), &BTreeSet::new())
}

#[test]
fn a_call_to_another_file_settles_the_named_doubt() {
    let call = r#"{"k":"call","file":0,"line":3,"col":9,"callee_file":2,"touch":[],"open":null}"#;
    let filter = filter_of(&[call]);
    assert_eq!(
        Filter::resolved_elsewhere(Some(&filter), B, AT),
        Some(false)
    );
}

#[test]
fn an_argument_that_can_run_the_target_keeps_the_execution_doubt() {
    let touch = r#"{"k":"call","file":0,"line":3,"col":9,"callee_file":2,"touch":[1],"open":null}"#;
    let open = r#"{"k":"call","file":0,"line":3,"col":9,"callee_file":2,"touch":[],"open":"fn"}"#;
    for call in [touch, open] {
        let filter = filter_of(&[call]);
        assert_eq!(Filter::resolved_elsewhere(Some(&filter), B, AT), Some(true));
    }
}

#[test]
fn a_call_to_the_target_or_an_unknown_place_settles_nothing() {
    let call = r#"{"k":"call","file":0,"line":3,"col":9,"callee_file":1,"touch":[],"open":null}"#;
    let filter = filter_of(&[call]);
    assert_eq!(Filter::resolved_elsewhere(Some(&filter), B, AT), None);
    assert_eq!(
        Filter::resolved_elsewhere(Some(&filter), B, ("crates/app/src/a.rs", 4, 9)),
        None
    );
    assert_eq!(Filter::resolved_elsewhere(None, B, AT), None);
}

#[test]
fn two_callees_at_one_place_settle_nothing() {
    let one = r#"{"k":"call","file":0,"line":3,"col":9,"callee_file":2,"touch":[],"open":null}"#;
    let two = r#"{"k":"call","file":0,"line":3,"col":9,"callee_file":0,"touch":[],"open":null}"#;
    let filter = filter_of(&[one, two]);
    assert_eq!(Filter::resolved_elsewhere(Some(&filter), B, AT), None);
}
