// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// One scan of the TypeScript fixtures in the process (AD-406): the derived request, the typed
// reply against the bytes of the binary's producer, and each named refusal.

use std::fs;
use std::io::Read;
use std::path::{Path, PathBuf};

use flate2::read::ZlibDecoder;

use super::*;
use crate::repository::tests::scratch;

const HEAD: &str = "0123456789abcdef0123456789abcdef01234567";
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
pub(super) fn repository(fixture: &str) -> PathBuf {
    let root = scratch(&format!("fixture-{fixture}"));
    copy(
        &Path::new(env!("CARGO_MANIFEST_DIR")).join(format!("../../fixtures/{fixture}")),
        &root,
    );
    fs::create_dir_all(root.join(".git/refs/heads")).unwrap();
    fs::write(root.join(".git/HEAD"), "ref: refs/heads/main\n").unwrap();
    fs::write(root.join(".git/refs/heads/main"), format!("{HEAD}\n")).unwrap();
    root
}

pub(super) fn identity(root: &str) -> Identity<'_> {
    Identity {
        root,
        config: "archkeel.toml",
        git_head: HEAD,
        dirty: false,
    }
}

fn refusal(root: &Path) -> Refusal {
    scan(&identity(root.to_str().unwrap()), 1 << 26)
        .err()
        .expect("the scan is refused")
}

/// The reply of the producer of the binary (`reply`), decoded, as JSON bytes.
pub(super) fn binary_bytes(request: &[u8]) -> Vec<u8> {
    let request = archkeel_wire::request::decode(request).unwrap();
    let mut wire = Vec::new();
    archkeel_typescript_collector::reply(
        &request,
        archkeel_typescript_collector::provenance(),
        archkeel_wire::protocol::reply_version(request.protocol_version),
        &mut wire,
    )
    .unwrap();
    let mut plain = Vec::new();
    ZlibDecoder::new(wire.as_slice())
        .read_to_end(&mut plain)
        .unwrap();
    let reply: archkeel_facts::envelope::Reply = serde_json::from_slice(&plain).unwrap();
    serde_json::to_vec(&reply).unwrap()
}

#[test]
fn each_fixture_scans_in_the_process_and_equals_the_reply_of_the_binary() {
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
        git_head: "f".repeat(40).leak(),
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
    let python = original.replace("language = \"typescript\"\n", "");
    fs::write(
        &config,
        python.replace("tsconfig = \"tsconfig.json\"\n", ""),
    )
    .unwrap();
    assert_eq!(refusal_part(&root), "profile");
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
    for profile in [Profile::Python, Profile::Dart] {
        let error = reply_of(profile, &request).unwrap_err();
        assert!(error.contains(profile.as_str()), "{error}");
        assert!(error.contains("no collector in the core process yet"));
    }
}
