// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// The scan request (AD-406): it takes only the scan identity, the core runs the collector, and a
// refused scan or a forged field never decides a run.

use std::fs;
use std::path::{Path, PathBuf};

use serde_json::json;

use archkeel_store::Ingested;

use super::*;

#[test]
fn missing_provenance_is_derived_and_a_false_clean_claim_is_refused() {
    let root = repository("provenance");
    let mut request = request(&root);
    request.as_object_mut().unwrap().remove("git_head");
    request.as_object_mut().unwrap().remove("dirty");
    let (clean, _) = frame(&request);
    assert_eq!(
        clean["self_test"]["collect"]["request"]["snapshot"]["dirty"],
        false
    );
    fs::write(root.join("untracked.txt"), "new file").unwrap();
    let (dirty, _) = frame(&request);
    assert_eq!(
        dirty["self_test"]["collect"]["request"]["snapshot"]["dirty"],
        true
    );
    request["dirty"] = json!(false);
    let (refused, names) = frame(&request);
    assert!(names);
    assert_eq!(refused["status"], "UNKNOWN");
    assert!(refused["self_test"]["collect"]["refused"]
        .as_str()
        .unwrap()
        .contains("dirty"));
    assert!(refused["self_test"]["contract"].get("refused").is_none());
}

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
    for args in [
        vec!["init", "-q"],
        vec!["add", "."],
        vec![
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-qm",
            "fixture",
        ],
    ] {
        let git = if cfg!(windows) {
            "C:/Program Files/Git/cmd/git.exe"
        } else {
            "/usr/bin/git"
        };
        assert!(std::process::Command::new(git)
            .args(args)
            .current_dir(&root)
            .status()
            .unwrap()
            .success());
    }
    fs::canonicalize(root).unwrap()
}

fn request(root: &Path) -> serde_json::Value {
    json!({
        "protocol": "archkeel-core-scan-1",
        "root": root.to_str().unwrap(),
        "config": "archkeel.toml",
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

fn ingested(change: impl FnOnce(&mut Value)) -> Ingested {
    let reply = crate::engine::tests::golden_reply_with(change);
    archkeel_store::ingest_reply(&reply, 1 << 30).ok().unwrap()
}

fn ours(value: &mut Value) {
    value["facts"]["adapter"]["code_digest"] = json!(CODE_DIGEST);
}

#[test]
fn the_in_process_trust_needs_the_profile_the_adapter_and_the_digest_of_this_build() {
    let trust = |profile, reply: &Ingested| in_process(profile)("shop".to_owned(), Some(reply));
    assert_eq!(trust(Profile::TypeScript, &ingested(ours)).gap, None);
    let refused = [
        trust(Profile::TypeScript, &ingested(|_| {})),
        trust(Profile::Rust, &ingested(ours)),
        trust(
            Profile::TypeScript,
            &ingested(|value| {
                ours(value);
                value["facts"]["adapter"]["name"] = json!("archkeel-rust-imports");
            }),
        ),
    ];
    for trust in refused {
        let gap = trust.gap.unwrap_or_default();
        assert!(gap.starts_with(PRODUCER_NOT_VERIFIED), "{gap}");
    }
}

#[test]
fn the_core_reads_the_inside_contracts_itself_and_names_a_missing_one() {
    let root = repository("inside");
    let path = root.join("architecture-contract.json");
    let mut contract: Value = serde_json::from_slice(&fs::read(&path).unwrap()).unwrap();
    for item in contract["components"].as_array_mut().unwrap() {
        if item["label"] == "domain" {
            item["inside"] = json!("inside.json");
        }
    }
    fs::write(&path, contract.to_string()).unwrap();
    let (missing, names_a_gap) = frame(&request(&root));
    assert!(names_a_gap);
    let wanted = missing["self_test"]["contract"]["missing"][0]
        .as_str()
        .unwrap()
        .to_owned();
    let component = json!({"id": "C-0", "label": "c0", "role": "component",
        "packages": ["shop.src.domain"], "responsibilities": ["Own it."],
        "forbidden_responsibilities": [], "provenance": ["docs/a.md"]});
    let rule = json!({"id": "IN", "kind": "complete_assignment", "source": "shop.src.domain",
        "rationale": "r", "provenance": ["docs/a.md"], "decided_by": "architect"});
    let inside = json!({"schema_version": "2.2.0", "components": [component], "rules": [rule]});
    fs::write(root.join(&wanted), inside.to_string()).unwrap();
    let (read, _) = frame(&request(&root));
    let rules = read["self_test"]["contract"]["rules"].as_object().unwrap();
    assert!(rules.keys().any(|rule| rule.ends_with("IN")), "{read}");
}

/// AD-406 review F2: a reply of another profile that names the adapter of the profile that ran
/// and the code digest of this build. The store accepts it (it holds the registered Rust set), so
/// the profile compare of `in_process` is the only check that refuses it.
#[test]
fn the_in_process_trust_refuses_a_reply_of_another_profile_with_the_adapter_of_this_one() {
    let foreign = ingested(|value| {
        ours(value);
        value["facts"]["profile"] = json!("archkeel-rust-imports");
        value["facts"]["capabilities"]["resolution_features"] = json!(["rust-crate-edges"]);
        value["facts"]["capabilities"]["constructs"] = json!([]);
        let kept = ["imports", "symbols", "unknowns"];
        let facts = &mut value["facts"];
        if let Some(sections) = facts["sections"].as_array_mut() {
            sections.retain(|section| kept.iter().any(|name| section["name"] == *name));
            sections
                .iter_mut()
                .filter_map(|section| section["records"].as_array_mut())
                .flatten()
                .for_each(|record| record["fact_ids"] = json!([]));
        }
        facts["capabilities"]["sections"] = json!(kept);
    });
    assert_eq!(
        foreign.reply().facts.adapter.name,
        Profile::TypeScript.as_str()
    );
    let gap = in_process(Profile::TypeScript)("shop".to_owned(), Some(&foreign)).gap;
    assert!(gap.is_some_and(|gap| gap.starts_with(PRODUCER_NOT_VERIFIED)));
}
