// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// The stable key of a gap (AD-546): what it is, not where it is.

use serde_json::json;

use archkeel_facts::{GapFact, Record};

use super::{collector, strip_line, Key};

fn record(kind: &str, line: i64, data: serde_json::Value, subject: &str) -> Record<GapFact> {
    let mut data = data;
    data["line"] = json!(line);
    serde_json::from_value(json!({
        "area": "analysis_coverage", "data": data, "evidence_class": "UNKNOWN",
        "evidence_ids": [], "fact_ids": [], "id": format!("COVERAGE-{line}"), "kind": kind,
        "provenance": [], "rule_ids": [],
        "subjects": [format!("{subject}:{line}")],
        "title": format!("{subject}:{line} could not be analyzed"),
    }))
    .expect("a gap record")
}

fn key(kind: &str, subject: &str, reason: &str) -> Key {
    Key {
        kind: kind.to_owned(),
        subject: subject.to_owned(),
        reason: reason.to_owned(),
    }
}

#[test]
fn a_file_failure_keeps_its_key_when_its_line_moves() {
    let data = |message: &str| json!({"file": "pkg/a.py", "message": message});
    let first = collector(&record(
        "SyntaxError",
        4,
        data("invalid syntax"),
        "pkg/a.py",
    ));
    let moved = collector(&record("SyntaxError", 40, data("another text"), "pkg/a.py"));
    assert_eq!(first, moved);
    assert_eq!(first, key("SyntaxError", "pkg/a.py", "SyntaxError"));
}

#[test]
fn a_collector_gap_is_keyed_by_its_module_and_reason_and_not_by_its_line() {
    let data = json!({"module": "pkg.mod", "reason": "dynamic_import: pickle.loads"});
    let first = collector(&record(
        "source_resolution_gap",
        3,
        data.clone(),
        "pkg/mod.py",
    ));
    let moved = collector(&record("source_resolution_gap", 90, data, "pkg/mod.py"));
    assert_eq!(first, moved);
    assert_eq!(
        first,
        key(
            "source_resolution_gap",
            "pkg.mod",
            "dynamic_import: pickle.loads"
        )
    );
}

#[test]
fn the_same_reason_in_another_module_or_another_reason_is_another_key() {
    let at = |module: &str, reason: &str| {
        let data = json!({"module": module, "reason": reason});
        collector(&record("source_resolution_gap", 1, data, "x.py"))
    };
    let base = at("pkg.a", "dynamic_import: pickle");
    assert_ne!(base, at("pkg.b", "dynamic_import: pickle"));
    assert_ne!(base, at("pkg.a", "dynamic_import: eval"));
}

#[test]
fn a_position_at_the_end_of_a_reason_is_not_in_the_key() {
    assert_eq!(
        strip_line("Syntax error in a.ts: unparseable construct at line 12"),
        "Syntax error in a.ts: unparseable construct"
    );
    assert_eq!(strip_line("lib/a.dart:7"), "lib/a.dart");
    assert_eq!(
        strip_line("dynamic_import: pickle"),
        "dynamic_import: pickle"
    );
    assert_eq!(strip_line("module 12"), "module 12");
    assert_eq!(strip_line("7"), "7");
}

#[test]
fn two_sites_of_one_key_are_counted_and_never_merged() {
    let mut gaps = super::Gaps::default();
    gaps.add(key("k", "s", "r"), 1);
    gaps.add(key("k", "s", "r"), 1);
    gaps.add(key("k", "t", "r"), 1);
    assert_eq!(gaps.keys[&key("k", "s", "r")], 2);
    assert_eq!(gaps.keys[&key("k", "t", "r")], 1);
    gaps.add(key("k", "s", "r"), 3);
    assert_eq!(gaps.keys[&key("k", "s", "r")], 5);
}
