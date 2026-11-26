// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Hostile bytes on the stdin of `archkeel-core scan` (#1001): each request is refused with a
// typed error or gives a frame that is not a PASS. None crashes, hangs or reads outside the root.

use std::fs;
use std::time::{Duration, Instant};

use serde_json::{json, Value};

use super::{repository, request};

/// The refusal text, or the status of the frame when the core did answer.
fn outcome(input: &[u8]) -> Result<String, String> {
    let started = Instant::now();
    let result = crate::scan_answer(input);
    assert!(started.elapsed() < Duration::from_secs(20), "a hang");
    match result {
        Ok(answered) => {
            let frame: Value = serde_json::from_slice(&answered.frame).expect("a frame is JSON");
            Ok(frame["status"].as_str().unwrap_or("").to_owned())
        }
        Err(error) => Err(error.to_string()),
    }
}

fn refused(input: &[u8]) -> String {
    let status = outcome(input).err();
    status.expect("expected a refusal, got a frame")
}

#[test]
fn malformed_and_truncated_json_is_refused() {
    let root = repository("hostile-json");
    let whole = request(&root).to_string();
    let mut inputs: Vec<Vec<u8>> = vec![
        Vec::new(),
        b"null".to_vec(),
        b"[]".to_vec(),
        b"\"x\"".to_vec(),
        b"{".to_vec(),
        b"\xff\xfe\x00".to_vec(),
        b"{\"protocol\":\"archkeel-core-scan-1\"}".to_vec(),
    ];
    // Every prefix is a truncated frame; a prefix is never a whole object.
    for cut in (0..whole.len()).step_by(7) {
        inputs.push(whole.as_bytes()[..cut].to_vec());
    }
    for input in inputs {
        refused(&input);
    }
}

#[test]
fn wrong_types_unknown_fields_and_a_wrong_protocol_are_refused() {
    let root = repository("hostile-types");
    for (field, replacement) in [
        ("root", json!(1)),
        ("root", json!(null)),
        ("config", json!(["archkeel.toml"])),
        ("dirty", json!("yes")),
        ("html", json!(1)),
        ("git_head", json!({})),
        ("part_of", json!("x")),
        ("part_of", json!({"href": "x"})),
        ("part_of", json!({"document": "x", "extra": 1})),
        ("extra", json!(1)),
        ("protocol", json!(1)),
        ("protocol", json!("archkeel-core-scan-2")),
    ] {
        let mut value = request(&root);
        value[field] = replacement;
        refused(value.to_string().as_bytes());
    }
}

#[test]
fn deep_nesting_and_a_very_long_string_are_refused_without_a_crash() {
    let root = repository("hostile-size");
    let deep = format!("{}1{}", "[".repeat(200_000), "]".repeat(200_000));
    refused(deep.as_bytes());
    let mut nested = request(&root);
    nested["part_of"] = serde_json::from_str(&format!(
        "{}{}",
        "{\"a\":".repeat(100),
        "1".to_owned() + &"}".repeat(100)
    ))
    .unwrap();
    refused(nested.to_string().as_bytes());
    for field in ["config", "git_head", "baseline"] {
        let mut long = request(&root);
        long[field] = json!("a".repeat(900_000));
        if let Ok(status) = outcome(long.to_string().as_bytes()) {
            assert_ne!(status, "PASS", "{field}");
        }
    }
}

#[test]
fn a_repeated_key_is_not_a_second_value() {
    let root = repository("hostile-duplicate");
    let text = format!(
        "{{\"protocol\":\"archkeel-core-scan-1\",\"root\":{},\"root\":\"/\",\"config\":\"archkeel.toml\"}}",
        json!(root.to_str().unwrap())
    );
    refused(text.as_bytes());
}

#[cfg(unix)]
#[test]
fn a_path_field_that_leaves_the_root_never_gives_a_pass() {
    let root = repository("hostile-paths");
    let outside = root.with_file_name(format!(
        "{}-outside",
        root.file_name().unwrap().to_str().unwrap()
    ));
    fs::create_dir_all(&outside).unwrap();
    fs::write(outside.join("archkeel.toml"), "[project]\n").unwrap();
    fs::write(outside.join("baseline.json"), "{}").unwrap();
    std::os::unix::fs::symlink(&outside, root.join("link")).unwrap();
    for (field, replacement) in [
        ("config", json!("../archkeel.toml")),
        (
            "config",
            json!(outside.join("archkeel.toml").to_str().unwrap()),
        ),
        ("config", json!("link/archkeel.toml")),
        ("config", json!("a\u{0}b")),
        ("config", json!("")),
        ("baseline", json!("../baseline.json")),
        (
            "baseline",
            json!(outside.join("baseline.json").to_str().unwrap()),
        ),
        ("baseline", json!("link/baseline.json")),
        ("baseline", json!("a\u{0}b")),
        ("root", json!("relative/root")),
        ("root", json!("/nonexistent-archkeel-root")),
        ("root", json!("a\u{0}b")),
    ] {
        let mut value = request(&root);
        value[field] = replacement;
        let text = value.to_string();
        match outcome(text.as_bytes()) {
            Err(_) => {}
            Ok(status) => assert_ne!(status, "PASS", "{field}: {text}"),
        }
    }
    fs::remove_dir_all(&outside).unwrap();
}
