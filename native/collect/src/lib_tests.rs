// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// One scan of the TypeScript fixtures in the process (AD-406): the derived request, the typed
// reply against the bytes of the binary's producer, and each named refusal.

use std::fs;
use std::io::Read;
use std::path::Path;

use flate2::read::ZlibDecoder;

use super::*;
use crate::repository::tests::scratch;

/// The TypeScript fixtures of the repository with a scan configuration.
const FIXTURES: [&str; 4] = [
    "H-typescript",
    "F-typescript-story",
    "H-uml-typescript",
    "L-nest-realworld",
];

pub(super) fn copy(from: &Path, to: &Path) {
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

/// A copy of a fixture with a Git directory whose `HEAD` names `HEAD` on `main`.
pub(super) fn repository(fixture: &str) -> crate::repository::tests::Scratch {
    let root = scratch(&format!("fixture-{fixture}"));
    copy(
        &Path::new(env!("CARGO_MANIFEST_DIR")).join(format!("../../fixtures/{fixture}")),
        &root,
    );
    commit(&root);
    root
}

pub(super) fn commit(root: &Path) {
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
        assert!(std::process::Command::new("git")
            .args(args)
            .current_dir(root)
            .status()
            .unwrap()
            .success());
    }
}

pub(super) fn identity(root: &str) -> Identity<'_> {
    Identity {
        root,
        config: "archkeel.toml",
        discover_root: false,
        git_head: Some(git::head(Path::new(root)).unwrap().leak()),
        dirty: Some(git::dirty(Path::new(root)).unwrap()),
    }
}

fn refusal(root: &Path) -> Refusal {
    scan(&identity(root.to_str().unwrap()), 1 << 26)
        .err()
        .expect("the scan is refused")
}

/// The reply of the producer of the binary (`reply`), decoded, as JSON bytes.
pub(super) fn binary_bytes(request: &[u8]) -> Vec<u8> {
    let wire = public_output(crate::worker::Worker::TypeScript, request);
    let mut plain = Vec::new();
    ZlibDecoder::new(wire.as_slice())
        .read_to_end(&mut plain)
        .unwrap();
    let reply: archkeel_facts::envelope::Reply = serde_json::from_slice(&plain).unwrap();
    serde_json::to_vec(&reply).unwrap()
}

pub(super) fn public_output(worker: crate::worker::Worker, request: &[u8]) -> Vec<u8> {
    use std::io::Write;
    use std::process::{Command, Stdio};
    let mut child = Command::new(crate::worker::executable(&worker).unwrap())
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .spawn()
        .unwrap();
    child.stdin.take().unwrap().write_all(request).unwrap();
    let out = child.wait_with_output().unwrap();
    assert!(out.status.success());
    out.stdout
}

#[test]
fn each_fixture_scans_in_the_worker_and_equals_the_public_reply() {
    for fixture in FIXTURES {
        let root = repository(fixture);
        let text = root.to_str().unwrap();
        let scanned = scan(&identity(text), 1 << 26)
            .map_err(|refusal| format!("{fixture}: {refusal}"))
            .unwrap();
        assert_eq!(scanned.profile, Profile::TypeScript);
        assert_eq!(scanned.request["snapshot"]["root"], text);
        assert_eq!(scanned.request["resolver"]["language"], "typescript");
        let bytes = serde_json::to_vec(&scanned.request).unwrap();
        let typed = serde_json::to_vec(&reply_of(scanned.profile, &bytes).unwrap()).unwrap();
        assert_eq!(typed, binary_bytes(&bytes), "{fixture}");
        assert_eq!(
            serde_json::to_vec(scanned.reply.reply()).unwrap(),
            typed,
            "{fixture}: the store keeps the typed reply as it is"
        );
        assert!(!scanned.contract.1.is_empty());
    }
}

#[test]
fn a_planted_environment_changes_no_byte_of_the_reply() {
    let root = repository("H-typescript");
    let text = root.to_str().unwrap();
    let request = serde_json::to_vec(&scan(&identity(text), 1 << 26).unwrap().request).unwrap();
    let before = serde_json::to_vec(&reply_of(Profile::TypeScript, &request).unwrap()).unwrap();
    // The planted faults of `plant.rs` read these variables only in a build with `dump`.
    std::env::set_var("ARCHKEEL_PLANT_SKIP", "src/catalog/index.ts:0");
    std::env::set_var("ARCHKEEL_PLANT_SCAN", "import");
    let after = serde_json::to_vec(&reply_of(Profile::TypeScript, &request).unwrap()).unwrap();
    std::env::remove_var("ARCHKEEL_PLANT_SKIP");
    std::env::remove_var("ARCHKEEL_PLANT_SCAN");
    assert_eq!(before, after);
    assert!(test_features().is_empty(), "this test build links dump");
}

#[test]
fn another_head_profile_or_collector_is_refused_by_name() {
    let root = repository("H-typescript");
    let text = root.to_str().unwrap();
    let other = Identity {
        git_head: Some("f".repeat(40).leak()),
        ..identity(text)
    };
    let refusal = scan(&other, 1 << 26)
        .err()
        .expect("another head is refused");
    assert_eq!(refusal.part, "git head");
    let config = root.join("archkeel.toml");
    let original = fs::read_to_string(&config).unwrap();
    fs::write(&config, original.replace("typescript", "python")).unwrap();
    assert_eq!(refusal_part(&root), "config");
    fs::write(&config, format!("{original}collector_argv = [\"/x\"]\n")).unwrap();
    assert_eq!(refusal_part(&root), "collector");
}

fn refusal_part(root: &Path) -> &'static str {
    refusal(root).part
}

#[test]
fn a_configuration_that_points_out_of_the_root_is_refused() {
    let root = repository("H-typescript");
    let config = root.join("archkeel.toml");
    let original = fs::read_to_string(&config).unwrap();
    let outside = root.parent().unwrap().join("outside-tsconfig.json");
    fs::write(&outside, "{}").unwrap();
    let replaced = |from: &str, to: &str| fs::write(&config, original.replace(from, to)).unwrap();
    replaced("\"tsconfig.json\"", "\"../outside-tsconfig.json\"");
    assert!(refusal(&root).reason.contains("safe POSIX relative path"));
    replaced("\"tsconfig.json\"", "\"link.json\"");
    #[cfg(unix)]
    std::os::unix::fs::symlink(&outside, root.join("link.json")).unwrap();
    assert!(refusal(&root)
        .reason
        .contains("TypeScript config is not a file"));
    replaced("roots = [\"src\"]", "roots = [\"up\"]");
    #[cfg(unix)]
    std::os::unix::fs::symlink("..", root.join("up")).unwrap();
    assert!(refusal(&root)
        .reason
        .contains("scan root is not a directory"));
    let identity = Identity {
        config: "../archkeel.toml",
        ..identity(root.to_str().unwrap())
    };
    assert_eq!(
        scan(&identity, 1 << 26).err().map(|r| r.part),
        Some("config")
    );
}

#[test]
fn a_build_with_a_test_feature_and_a_panic_of_the_collector_are_refusals() {
    assert_eq!(built(&[]), Ok(()));
    assert_eq!(built(&["dump"]).unwrap_err().part, "build");
    let planted: Option<u8> = std::hint::black_box(None);
    let panicked = run::isolated(move || planted.expect("planted"));
    assert_eq!(
        panicked,
        Err(refused(
            "collector",
            "the collector stopped with a panic: planted"
        ))
    );
}

#[test]
fn each_refusal_kind_keeps_its_message() {
    let mut refusal = refused("parse work", "parse_work_limit: src/main.rs");
    assert_eq!(
        refusal.to_string(),
        "collect: unsupported: parse work: parse_work_limit: src/main.rs"
    );
    refusal.kind = RefusalKind::ParseWork;
    assert_eq!(
        refusal.to_string(),
        "collect: parse_work_limit: src/main.rs"
    );
}

#[test]
fn a_contract_over_its_budget_is_refused() {
    let root = repository("H-typescript");
    let refusal = scan(&identity(root.to_str().unwrap()), 10)
        .err()
        .expect("the contract is refused");
    assert_eq!(refusal.part, "contract");
    assert_eq!(
        refusal.to_string(),
        "collect: unsupported: contract: architecture-contract.json holds more than 10 bytes"
    );
}

#[test]
fn the_profile_selects_its_strict_decoder_and_refuses_unlinked_collectors() {
    let root = repository("H-typescript");
    let scanned = scan(&identity(root.to_str().unwrap()), 1 << 26).unwrap();
    let request = serde_json::to_vec(&scanned.request).unwrap();
    assert!(run::collect(Profile::Rust, &request).is_err());
    let error = reply_of(Profile::Dart, &request).unwrap_err();
    assert!(error.contains("Dart resolver"), "{error}");
    let error = reply_of(Profile::Python, &request).unwrap_err();
    assert!(error.contains("Python resolver"), "{error}");
}

/// AD-688: a reply that names another profile keeps the block of its collector, so the store
/// accepts it; the check of the profile that it names refuses its records, and the trust of the
/// core names the profile (`scan::in_process`).
#[test]
fn a_reply_that_names_the_python_or_the_dart_profile_meets_the_check_of_that_collector() {
    let root = repository(FIXTURES[0]);
    let scanned = scan(&identity(root.to_str().unwrap()), 1 << 26).unwrap();
    for (profile, reason) in [
        (
            Profile::Python,
            "the Python target has no standard library table",
        ),
        (Profile::Dart, "a Dart import"),
    ] {
        let mut reply = scanned.reply.reply().clone();
        reply.facts.profile = profile;
        let ingested = archkeel_store::ingest_typed(reply).unwrap();
        let refused = crate::check(&ingested.reply().facts)
            .err()
            .unwrap_or_default();
        assert!(refused.contains(reason), "{profile:?}: {refused}");
    }
}

// AD-1119: the Explorer leaves test sources out of a Python or TypeScript scan unless the config
// states the scope. `validate` and `report` keep the tests.
fn test_scope(root: &Path, explorer: bool) -> serde_json::Value {
    let text = root.to_str().unwrap();
    let scanned = scan_with_options(&identity(text), 1 << 26, None, explorer).unwrap();
    scanned.request["scope"]["exclude_test_sources"].clone()
}

#[test]
fn the_explorer_excludes_test_sources_by_default_and_the_config_decides_otherwise() {
    let root = repository("H-typescript");
    assert_eq!(test_scope(&root, false), serde_json::Value::Null);
    assert_eq!(test_scope(&root, true), serde_json::Value::Bool(true));
    let config = root.join("archkeel.toml");
    let text = fs::read_to_string(&config).unwrap();
    fs::write(&config, format!("{text}exclude_test_sources = false\n")).unwrap();
    commit(&root);
    assert_eq!(test_scope(&root, true), serde_json::Value::Null);
    fs::write(&config, format!("{text}exclude_test_sources = true\n")).unwrap();
    commit(&root);
    assert_eq!(test_scope(&root, false), serde_json::Value::Bool(true));
    // A removed file with an implicit scope holds the verdict; a stated scope does not (AD-1119).
    fs::write(&config, &text).unwrap();
    fs::write(root.join("src/x.test.ts"), "export const x = 1;\n").unwrap();
    commit(&root);
    let hold = |explorer| {
        let text = root.to_str().unwrap();
        scan_with_options(&identity(text), 1 << 26, None, explorer)
            .unwrap()
            .test_scope_hold()
    };
    assert!(hold(true).is_some_and(|why| why.contains("src/x.test.ts")));
    assert!(hold(false).is_none());
    fs::write(&config, format!("{text}exclude_test_sources = true\n")).unwrap();
    commit(&root);
    assert!(hold(true).is_none());
}

// AD-1420: a missing entry refuses; a stated entry reaches the collector in the request.
#[test]
fn a_browser_entry_refuses_when_it_is_missing_and_reaches_the_request_when_it_is_there() {
    let root = repository("H-typescript");
    let config = root.join("archkeel.toml");
    let text = fs::read_to_string(&config).unwrap();
    fs::write(
        &config,
        format!("{text}browser_entry = \"web/index.html\"\n"),
    )
    .unwrap();
    commit(&root);
    let path = root.to_str().unwrap();
    let refused = scan_with_options(&identity(path), 1 << 26, None, false).err();
    let why = refused
        .map(|refusal| refusal.to_string())
        .unwrap_or_default();
    assert!(
        why.contains("scan browser entry is not a file: web/index.html"),
        "{why}"
    );
    fs::create_dir_all(root.join("web")).unwrap();
    fs::write(root.join("web/index.html"), "<!doctype html>\n").unwrap();
    commit(&root);
    let config = read_config(&root_of(&identity(path)).unwrap(), "archkeel.toml").unwrap();
    assert_eq!(
        request(&identity(path), &config)["resolver"]["browser"],
        serde_json::json!({"entry": "web/index.html", "assets": ["web"]})
    );
}
