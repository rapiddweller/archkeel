// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// AD-406, issue #1095 slice 2: one producer, two validated doors.

use std::fs;
use std::path::Path;

use super::*;
use crate::tests::{copy, identity};

pub(super) fn repository() -> std::path::PathBuf {
    let root = crate::repository::tests::scratch("rust");
    fs::create_dir_all(root.join("src")).unwrap();
    fs::create_dir_all(root.join(".git")).unwrap();
    fs::write(
        root.join(".git/HEAD"),
        "0123456789abcdef0123456789abcdef01234567",
    )
    .unwrap();
    fs::write(
        root.join("Cargo.toml"),
        "[package]\nname = \"example\"\nversion = \"0.0.0\"\n",
    )
    .unwrap();
    fs::write(root.join("src/lib.rs"), "pub fn example() {}\n").unwrap();
    fs::write(root.join("archkeel.toml"), "[scan]\nlanguage = \"rust\"\nroots = [\".\"]\nnamespace = \"app\"\ncontract = \"contract.json\"\n").unwrap();
    fs::write(root.join("contract.json"), "{}").unwrap();
    root
}

fn equal(request: &[u8]) {
    let decoded = archkeel_wire::request::decode_rust(request).unwrap();
    let wire = std::thread::Builder::new()
        .stack_size(256 << 20)
        .spawn(move || {
            archkeel_rust_collector::reply(
                &decoded,
                archkeel_rust_collector::provenance(),
                archkeel_wire::protocol::reply_version(decoded.protocol_version),
            )
        })
        .unwrap()
        .join()
        .unwrap()
        .unwrap();
    let binary = archkeel_store::ingest_reply(&wire, 1 << 30).unwrap();
    let linked = run::collect(Profile::Rust, request).unwrap();
    assert_eq!(
        serde_json::to_vec(linked.reply()).unwrap(),
        serde_json::to_vec(binary.reply()).unwrap(),
        "both store doors must keep byte-equal canonical facts"
    );
}

#[test]
fn the_rust_fixtures_use_the_same_validated_facts_and_request() {
    for exclude in [false, true] {
        let root = repository();
        if exclude {
            let config = root.join("archkeel.toml");
            let text = fs::read_to_string(&config).unwrap();
            fs::write(config, format!("{text}exclude_test_sources = true\n")).unwrap();
        }
        let scanned = scan(&identity(root.to_str().unwrap()), 1 << 26).unwrap();
        assert_eq!(scanned.profile, Profile::Rust);
        assert_eq!(scanned.request["resolver"], json!({"language": "rust"}));
        equal(&serde_json::to_vec(&scanned.request).unwrap());
    }
}

#[test]
fn the_native_workspace_collects_without_a_shell_reply() {
    let root = crate::repository::tests::scratch("native");
    let source = Path::new(env!("CARGO_MANIFEST_DIR")).join("..");
    fs::create_dir_all(root.join("native")).unwrap();
    for entry in fs::read_dir(source).unwrap() {
        let entry = entry.unwrap();
        if entry.file_name() == "target" {
            continue;
        }
        let target = root.join("native").join(entry.file_name());
        if entry.file_type().unwrap().is_dir() {
            copy(&entry.path(), &target);
        } else {
            fs::copy(entry.path(), target).unwrap();
        }
    }
    fs::create_dir_all(root.join(".git")).unwrap();
    let head = "0123456789abcdef0123456789abcdef01234567";
    fs::write(root.join(".git/HEAD"), head).unwrap();
    let identity = Identity {
        config: "native/archkeel.toml",
        ..identity(root.to_str().unwrap())
    };
    let scanned = scan(&identity, 1 << 26).unwrap();
    assert_eq!(scanned.profile, Profile::Rust);
    assert!(
        scanned.reply.reply().facts.files.len() > 200,
        "{} files",
        scanned.reply.reply().facts.files.len()
    );
    equal(&serde_json::to_vec(&scanned.request).unwrap());
}

#[test]
fn the_rust_corpus_uses_byte_equal_facts_through_both_store_doors() {
    // The Python corpus test keeps every materialized repository alive during this test.
    let Some(manifest) = std::env::var_os("ARCHKEEL_COLLECT_RUST_REQUESTS") else {
        return;
    };
    let cases: Vec<(String, Value)> = serde_json::from_slice(&fs::read(manifest).unwrap()).unwrap();
    assert!(!cases.is_empty());
    for (name, request) in &cases {
        eprintln!("Rust fact parity: {name}");
        equal(&serde_json::to_vec(request).unwrap());
    }
    eprintln!("Rust fact parity: {} equal; 0 differences", cases.len());
}

fn hostile_gap(text: &str, reason: &str) {
    let root = repository();
    let config = fs::read(root.join("archkeel.toml")).unwrap();
    let config = config::parse(&config, "archkeel.toml").unwrap();
    let request = request(&identity(root.to_str().unwrap()), &config);
    let payload = serde_json::to_vec(&request).unwrap();
    let source = root.join("src/lib.rs");
    fs::write(&source, text).unwrap();
    equal(&payload);
    let collected = run::collect(Profile::Rust, &payload).unwrap();
    let coverage = &collected.reply().facts.coverage;
    assert!(!coverage.full_scope);
    assert!(coverage.gaps.iter().any(|gap| gap.title.contains(reason)));
}

#[test]
fn a_huge_rust_file_gives_a_named_size_gap() {
    hostile_gap(&" ".repeat(5 << 20), "Source file over the size limit");
}

#[test]
fn deeply_nested_rust_gives_a_named_nesting_gap() {
    let text = format!(
        "fn hostile() {{ {}0{}; }}",
        "(".repeat(2000),
        ")".repeat(2000)
    );
    hostile_gap(&text, "Brackets nest deeper than 256");
}
