// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Compare the private worker with the in-process TypeScript collector.

use std::io::Write;
use std::path::Path;
use std::process::{Command, Stdio};

use archkeel_facts::envelope::Dirty;
use archkeel_facts::request::{Scope, Snapshot, TypeScriptRequest, TypeScriptSettings};
use archkeel_snapshot::test_tree::Tree;
use archkeel_wire::protocol::Version;
use archkeel_wire::worker::{read_rust_v1, RUST_WORKER_V1};

#[test]
fn private_worker_preserves_the_typed_reply_of_the_reference_project() {
    let root = Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../fixtures/H-typescript")
        .canonicalize()
        .unwrap();
    let request = TypeScriptRequest {
        protocol_version: Version::V9,
        snapshot: Snapshot {
            root: root.to_str().unwrap().to_owned(),
            git_head: "a".repeat(40),
            dirty: Dirty::Known(false),
        },
        scope: Scope {
            roots: vec!["src".to_owned()],
            namespace: "shop".to_owned(),
            exclude_test_sources: Some(false),
        },
        resolver: TypeScriptSettings {
            tsconfig: "tsconfig.json".to_owned(),
            bundler: false,
            browser: None,
        },
    };
    assert_worker_matches(&request, false).unwrap();
}

#[test]
fn private_worker_preserves_excluded_test_sources() {
    let tree = Tree::new(&[
        ("tsconfig.json", "{}"),
        ("src/latest.ts", ""),
        ("src/a.test.ts", ""),
    ]);
    let request = TypeScriptRequest {
        protocol_version: Version::V9,
        snapshot: Snapshot {
            root: tree.path(),
            git_head: "a".repeat(40),
            dirty: Dirty::Known(false),
        },
        scope: Scope {
            roots: vec!["src".to_owned()],
            namespace: "shop".to_owned(),
            exclude_test_sources: Some(true),
        },
        resolver: TypeScriptSettings {
            tsconfig: "tsconfig.json".to_owned(),
            bundler: false,
            browser: None,
        },
    };
    assert_worker_matches(&request, true).unwrap();
}

fn assert_worker_matches(
    request: &TypeScriptRequest,
    excluded: bool,
) -> Result<(), Box<dyn std::error::Error>> {
    let expected = archkeel_typescript_collector::typed_reply(
        request,
        archkeel_typescript_collector::provenance(),
        Version::V9,
    )?;
    assert!(expected.facts.profile_limits.is_some());
    assert!(expected.facts.scope_premise.is_some());
    assert!(!expected.facts.sections.is_empty());
    assert!(!expected.facts.evidence.is_empty());
    if excluded {
        assert_eq!(expected.facts.excluded_sources, ["src/a.test.ts"]);
    }

    let mut worker = Command::new(env!("CARGO_BIN_EXE_archkeel-typescript-collector"))
        .arg(RUST_WORKER_V1)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .spawn()?;
    let stdin = worker.stdin.as_mut().ok_or("worker stdin is unavailable")?;
    serde_json::to_writer(
        &mut *stdin,
        &serde_json::json!({
            "protocol_version": request.protocol_version,
            "snapshot": request.snapshot,
            "scope": request.scope,
            "resolver": {
                "language": "typescript",
                "tsconfig": request.resolver.tsconfig,
            },
        }),
    )?;
    stdin.write_all(b"\n")?;
    stdin.flush()?;
    let actual = read_rust_v1(worker.stdout.take().ok_or("worker stdout is unavailable")?)??;
    assert!(worker.wait()?.success());
    assert_eq!(actual, expected);
    Ok(())
}
