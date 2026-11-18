// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// AD-406, issue #1095 slice 2: one producer, two validated doors.

use std::fs;
use std::path::Path;

use super::*;
use crate::tests::{commit, copy, identity};
use archkeel_facts::envelope::LimitSupport;

pub(super) fn repository() -> std::path::PathBuf {
    let root = crate::repository::tests::scratch("rust");
    fs::create_dir_all(root.join("src")).unwrap();
    fs::write(
        root.join("Cargo.toml"),
        "[package]\nname = \"example\"\nversion = \"0.0.0\"\n",
    )
    .unwrap();
    fs::write(root.join("src/lib.rs"), "pub fn example() {}\n").unwrap();
    fs::write(root.join("archkeel.toml"), "[scan]\nlanguage = \"rust\"\nroots = [\".\"]\nnamespace = \"app\"\ncontract = \"contract.json\"\n").unwrap();
    fs::write(root.join("contract.json"), "{}").unwrap();
    commit(&root);
    root
}

pub(super) fn public_reply(request: &[u8]) -> archkeel_store::Ingested {
    use std::io::Write;
    use std::process::{Command, Stdio};
    let mut child = Command::new(crate::rust_worker::executable().unwrap())
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .spawn()
        .unwrap();
    child.stdin.take().unwrap().write_all(request).unwrap();
    let out = child.wait_with_output().unwrap();
    assert!(out.status.success());
    archkeel_store::ingest_reply(&out.stdout, 1 << 30).unwrap()
}

fn equal(request: &[u8]) {
    let binary = public_reply(request);
    let linked = run::collect(Profile::Rust, request).unwrap();
    // AD-604: only the linked reply states its routes (as the Python survey of AD-504); each
    // record and every other fact of both doors is the same.
    let mut stated = linked.reply().clone();
    let limits = stated.facts.profile_limits.take().unwrap();
    assert_eq!(limits.interface_boundary, LimitSupport::Supported);
    assert_eq!(limits.dependency_symbols, LimitSupport::Supported);
    let features = &mut stated.facts.capabilities.resolution_features;
    assert_eq!(features.pop().as_deref(), Some("rust-item-routes-v1"));
    assert_eq!(
        serde_json::to_vec(&stated).unwrap(),
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
    commit(&root);
    let identity = Identity {
        config: "native/archkeel.toml",
        ..identity(root.to_str().unwrap())
    };
    let scanned = scan(&identity, 1 << 26).unwrap();
    assert_eq!(scanned.profile, Profile::Rust);
    // The public encoding omits both; only the private worker frame carries them (AD-881).
    let facts = &scanned.reply.reply().facts;
    assert!(facts.scope_premise.is_some());
    assert!(
        facts
            .coverage
            .gaps
            .iter()
            .any(|gap| gap.data.data().dispatch),
        "no dispatch flag crossed the worker boundary"
    );
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
        "(".repeat(300),
        ")".repeat(300)
    );
    hostile_gap(&text, "Brackets nest deeper than 256");
}

/// The validation table of the Rust collector (AD-688; `evaluate.py:1055-1056`, AD-604): the
/// sections `imports` and `unknowns`, optionally `symbols`, no construct capability, and an
/// interface statement exactly with the routes feature.
#[test]
fn the_table_of_the_rust_collector_registers_its_sections_and_binds_the_interface() {
    use archkeel_facts::envelope::{ConstructCapability, ConstructSupport, SectionName};
    let root = repository();
    let scanned = scan(&identity(root.to_str().unwrap()), 1 << 26).unwrap();
    let payload = serde_json::to_vec(&scanned.request).unwrap();
    let reply = run::reply_of(Profile::Rust, &payload).unwrap();
    let refused = |reply: archkeel_facts::envelope::Reply| {
        archkeel_store::ingest_typed(reply)
            .err()
            .unwrap_or_default()
    };
    assert_eq!(refused(reply.clone()), "");
    let not_registered = "source sections or resolution features are not registered";
    let mut unknowns = reply.clone();
    unknowns
        .facts
        .capabilities
        .sections
        .retain(|name| *name != SectionName::Unknowns);
    unknowns
        .facts
        .sections
        .retain(|section| section.name() != "unknowns");
    assert_eq!(refused(unknowns), not_registered);
    let mut construct = reply.clone();
    construct
        .facts
        .capabilities
        .constructs
        .push(ConstructCapability {
            name: "assert".to_owned(),
            status: ConstructSupport::Supported,
        });
    assert_eq!(refused(construct), not_registered);
    let mut routes = reply;
    routes.facts.capabilities.resolution_features.pop();
    if let Some(limits) = routes.facts.profile_limits.as_mut() {
        limits.dependency_symbols = archkeel_facts::envelope::LimitSupport::Unsupported;
    }
    assert_eq!(
        refused(routes),
        "an interface statement holds exactly with the feature rust-item-routes-v1"
    );
}
