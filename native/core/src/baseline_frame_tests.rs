// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// The baseline part of a scan frame (AD-546): write, read, compare, and the refusals. Each test
// runs the real collector on a copy of a fixture.

use std::fs;
use std::path::Path;

use serde_json::{json, Value};

use crate::scan::{
    answer,
    tests::{repository, request},
};

fn frame(root: &Path, extra: Value) -> Value {
    let mut request = request(root);
    for (key, value) in extra.as_object().unwrap() {
        request[key] = value.clone();
    }
    let answered = answer(request.to_string().as_bytes()).expect("a frame");
    serde_json::from_slice(&answered.frame).expect("JSON")
}

fn written(root: &Path) -> String {
    let found = frame(root, json!({"write_baseline": true}));
    found["baseline"]["file"]
        .as_str()
        .expect("the bytes")
        .to_owned()
}

fn rewrite(root: &Path, change: impl FnOnce(&mut Value)) {
    let mut document: Value = serde_json::from_str(&written(root)).unwrap();
    change(&mut document);
    fs::write(root.join("b.json"), document.to_string()).unwrap();
}

fn part(root: &Path) -> Value {
    frame(root, json!({"baseline": "b.json"}))["baseline"].clone()
}

#[test]
fn a_run_written_and_read_back_has_no_difference_and_the_same_bytes() {
    let root = repository("base-round");
    let first = written(&root);
    assert!(first.contains("\"schema_version\": \"1.4.0\""));
    assert_eq!(first, written(&root));
    fs::write(root.join("b.json"), &first).unwrap();
    let found = part(&root);
    assert_eq!(found["state"], "current", "{found}");
    assert_eq!(found["new"], json!([]));
    assert_eq!(found["gone"], json!([]));
    let unknown = !serde_json::from_str::<Value>(&first).unwrap()["unknowns"]
        .as_array()
        .unwrap()
        .is_empty();
    assert_eq!(found["exit_code"], if unknown { 2 } else { 0 });
}

#[test]
fn a_blank_line_above_every_source_line_does_not_change_the_written_bytes() {
    let root = repository("base-moved");
    let before = written(&root);
    for entry in walk(&root) {
        let text = fs::read_to_string(&entry).unwrap();
        fs::write(&entry, format!("\n{text}")).unwrap();
    }
    assert_eq!(before, written(&root));
}

fn walk(root: &Path) -> Vec<std::path::PathBuf> {
    let mut found = Vec::new();
    let mut pending = vec![root.to_path_buf()];
    while let Some(dir) = pending.pop() {
        for entry in fs::read_dir(dir).unwrap().map(Result::unwrap) {
            let path = entry.path();
            if path.is_dir() {
                if entry.file_name() != ".git" && entry.file_name() != "node_modules" {
                    pending.push(path);
                }
            } else if path.extension().is_some_and(|ext| ext == "ts") {
                found.push(path);
            }
        }
    }
    found
}

#[test]
fn an_entry_that_the_run_lacks_is_stale_and_one_that_the_file_lacks_is_new() {
    let root = repository("base-two-way");
    rewrite(&root, |document| {
        let list = document["unknowns"].as_array_mut().unwrap();
        list.push(json!({"kind": "zz", "subject": "gone", "reason": "gone"}));
    });
    let found = part(&root);
    assert_eq!(
        (found["state"].as_str(), found["exit_code"].as_u64()),
        (Some("drift"), Some(1))
    );
    assert_eq!(found["gone"][0]["subject"], "gone");
    rewrite(&root, |document| {
        let list = document["unknowns"].as_array_mut().unwrap();
        if !list.is_empty() {
            list.remove(0);
        }
    });
    let first = written(&root);
    if serde_json::from_str::<Value>(&first).unwrap()["unknowns"]
        .as_array()
        .unwrap()
        .is_empty()
    {
        return;
    }
    let found = part(&root);
    assert_eq!(
        (found["state"].as_str(), found["exit_code"].as_u64()),
        (Some("drift"), Some(1))
    );
    assert_eq!(found["new"].as_array().unwrap().len(), 1);
}

#[test]
fn a_damaged_baseline_is_red_with_its_entry_and_never_a_silent_nothing_accepted() {
    let root = repository("base-damaged");
    let good: Value = serde_json::from_str(&written(&root)).unwrap();
    let entry = json!({"kind": "a", "subject": "b", "reason": "c"});
    let cases = [
        ("not json", "{".to_owned(), "b.json"),
        (
            "duplicate",
            with(&good, |d| d["unknowns"] = json!([entry, entry])),
            "repeats",
        ),
        (
            "unsorted",
            with(&good, |d| {
                d["unknowns"] = json!([{"kind": "b", "subject": "b", "reason": "c"}, entry])
            }),
            "not sorted",
        ),
        (
            "unknown field",
            with(
                &good,
                |d| {
                    d["unknowns"] = json!([{"kind": "a", "subject": "b", "reason": "c", "line": 4}])
                },
            ),
            "fields mismatch",
        ),
        (
            "count 0",
            with(
                &good,
                |d| {
                    d["unknowns"] =
                        json!([{"kind": "a", "subject": "b", "reason": "c", "count": 0}])
                },
            ),
            "at least 1",
        ),
        (
            "no unknowns field",
            with(&good, |d| {
                d.as_object_mut().unwrap().remove("unknowns");
            }),
            "fields mismatch",
        ),
        (
            "schema",
            with(&good, |d| d["schema_version"] = json!("1.5.0")),
            "cannot be read",
        ),
    ];
    for (name, text, needle) in cases {
        fs::write(root.join("b.json"), text).unwrap();
        let found = part(&root);
        assert_eq!(found["state"], "invalid", "{name}");
        assert_eq!(found["exit_code"], 1, "{name}");
        let reason = found["gaps"][0]["reason"].as_str().unwrap();
        assert!(reason.contains(needle), "{name}: {reason}");
    }
}

fn with(document: &Value, change: impl FnOnce(&mut Value)) -> String {
    let mut copy = document.clone();
    change(&mut copy);
    copy.to_string()
}

#[test]
fn a_missing_baseline_or_one_outside_the_repository_is_red() {
    let root = repository("base-missing");
    for path in ["absent.json", "../outside.json"] {
        let found = frame(&root, json!({"baseline": path}))["baseline"].clone();
        assert_eq!(
            (found["state"].as_str(), found["exit_code"].as_u64()),
            (Some("invalid"), Some(1)),
            "{path}"
        );
    }
}

#[test]
fn the_frame_lists_each_gap_of_the_rules_with_its_kind_from_the_core() {
    let root = repository("base-gaps");
    let found = frame(&root, json!({}));
    let rules = found["unsupported"]["rules"].clone();
    let gaps = found["gaps"].as_array().expect("a gaps list");
    match rules {
        Value::Object(each) => {
            assert_eq!(gaps.len(), each.len());
            for gap in gaps {
                assert_eq!(each[gap["subject"].as_str().unwrap()], gap["reason"]);
                assert!(gap["kind"].is_string());
            }
        }
        Value::String(text) => assert_eq!(gaps[0]["reason"], text),
        other => panic!("unexpected {other}"),
    }
    assert!(found.get("baseline").is_none());
}
