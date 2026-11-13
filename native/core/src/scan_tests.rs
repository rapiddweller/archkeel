// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// The scan request (AD-406): it takes only the scan identity, the core runs the collector, and a
// refused scan or a forged field never decides a run.

use std::fs;
use std::path::{Path, PathBuf};

use serde_json::json;

use super::*;

const HEAD: &str = "89abcdef0123456789abcdef0123456789abcdef";

fn copy(from: &Path, to: &Path) {
    fs::create_dir_all(to).unwrap();
    for entry in fs::read_dir(from).unwrap() {
        let entry = entry.unwrap();
        let target = to.join(entry.file_name());
        if entry.file_type().unwrap().is_dir() {
            copy(&entry.path(), &target);
        } else {
            fs::copy(entry.path(), target).unwrap();
        }
    }
}

/// A copy of the H-typescript fixture with a Git directory, canonical.
fn repository(name: &str) -> PathBuf {
    let root =
        std::env::temp_dir().join(format!("archkeel-core-scan-{name}-{}", std::process::id()));
    let _ = fs::remove_dir_all(&root);
    let fixture = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../fixtures/H-typescript");
    copy(&fixture, &root);
    fs::create_dir_all(root.join(".git")).unwrap();
    fs::write(root.join(".git/HEAD"), format!("{HEAD}\n")).unwrap();
    fs::canonicalize(root).unwrap()
}

fn request(root: &Path) -> serde_json::Value {
    json!({
        "protocol": "archkeel-core-scan-1",
        "root": root.to_str().unwrap(),
        "config": "archkeel.toml",
        "git_head": HEAD,
        "dirty": false,
    })
}

fn frame(request: &serde_json::Value) -> (Value, bool) {
    let answered = answer(request.to_string().as_bytes()).unwrap();
    (
        serde_json::from_slice(&answered.frame).unwrap(),
        answered.names_a_gap,
    )
}

#[test]
fn the_core_runs_the_collector_and_derives_the_request() {
    let root = repository("decide");
    let (frame, _) = frame(&request(&root));
    let derived = derived(&frame).unwrap();
    assert_eq!(derived["protocol_version"], "8.0.0");
    assert_eq!(derived["snapshot"]["root"], root.to_str().unwrap());
    assert_eq!(
        derived["scope"],
        json!({"roots": ["src"], "namespace": "shop"})
    );
    assert_eq!(
        derived["resolver"],
        json!({"language": "typescript", "tsconfig": "tsconfig.json"})
    );
    assert!(frame["self_test"]["reply"]["files"].as_u64().unwrap() > 0);
    let rules = frame["rules"].as_object().unwrap();
    assert!(!rules.is_empty());
    // The core trusts the reply that it made: no rule names the producer.
    let named = frame["unsupported"]["rules"].to_string();
    assert!(!named.contains(PRODUCER_NOT_VERIFIED), "{named}");
}

#[test]
fn a_scan_request_with_a_reply_or_a_trust_field_is_refused() {
    let root = repository("forged");
    for (field, value) in [
        ("reply", json!({"hex": "78"})),
        ("code_digest", json!(CODE_DIGEST)),
        ("producer", json!("trusted")),
        ("roots", json!(["src"])),
        ("collector_argv", json!(null)),
    ] {
        let mut forged = request(&root);
        forged[field] = value;
        let Err(error) = answer(forged.to_string().as_bytes()) else {
            unreachable_frame(field);
            continue;
        };
        assert!(error.contains("unknown field"), "{field}: {error}");
    }
    let mut old = request(&root);
    old["protocol"] = json!("archkeel-core-check-2");
    assert!(answer(old.to_string().as_bytes())
        .err()
        .is_some_and(|error| error.contains("unknown protocol")));
}

fn unreachable_frame(field: &str) {
    assert_eq!(field, "", "the scan request accepts the field {field}");
}

#[test]
fn a_refused_scan_names_the_collect_part_and_decides_nothing() {
    let root = repository("refused");
    let config = root.join("archkeel.toml");
    let text = fs::read_to_string(&config).unwrap();
    fs::write(&config, format!("{text}collector_argv = [\"/x\"]\n")).unwrap();
    let (frame, names_a_gap) = frame(&request(&root));
    assert!(names_a_gap);
    assert_eq!(frame["status"], "UNKNOWN");
    let refused = frame["self_test"]["collect"]["refused"].as_str().unwrap();
    assert!(
        refused.starts_with("collect: unsupported: collector: "),
        "{refused}"
    );
    let mut other = request(&root);
    other["git_head"] = json!("f".repeat(40));
    fs::write(&config, text).unwrap();
    let (frame, names_a_gap) = self::frame(&other);
    assert!(names_a_gap);
    let refused = frame["self_test"]["collect"]["refused"].as_str().unwrap();
    assert!(
        refused.starts_with("collect: unsupported: git head: "),
        "{refused}"
    );
}

#[test]
fn a_native_directory_in_the_repository_and_the_path_change_nothing() {
    let root = repository("redirect");
    let (before, _) = frame(&request(&root));
    // A planted collector beside the sources and an empty PATH: the core starts no program.
    fs::create_dir_all(root.join("_native")).unwrap();
    fs::write(
        root.join("_native/archkeel-typescript-collector"),
        "#!/bin/sh\nexit 0\n",
    )
    .unwrap();
    let path = std::env::var_os("PATH");
    std::env::set_var("PATH", "");
    let (after, _) = frame(&request(&root));
    if let Some(path) = path {
        std::env::set_var("PATH", path);
    }
    assert_eq!(before["rules"], after["rules"]);
    assert_eq!(before["self_test"]["reply"], after["self_test"]["reply"]);
}
