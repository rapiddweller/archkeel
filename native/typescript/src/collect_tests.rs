// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: Explore with a 9.0.0 request (AD-313). A scope that holds only test sources must not
// read as a complete scan of zero files.

use archkeel_facts::envelope::{Dirty, Profile};
use archkeel_facts::request::{Scope, Snapshot as SnapshotRequest, TypeScriptSettings};
use archkeel_wire::protocol::Version;

use super::*;
use archkeel_snapshot::test_tree::Tree;

fn request(tree: &Tree, exclude_test_sources: bool) -> TypeScriptRequest {
    TypeScriptRequest {
        protocol_version: Version::V9,
        snapshot: SnapshotRequest {
            root: tree.path(),
            git_head: "a".repeat(40),
            dirty: Dirty::Known(false),
        },
        scope: Scope {
            roots: vec!["src".to_owned()],
            namespace: "shop".to_owned(),
            exclude_test_sources: Some(exclude_test_sources),
        },
        resolver: TypeScriptSettings {
            tsconfig: "tsconfig.json".to_owned(),
            bundler: false,
        },
    }
}

fn provenance() -> Provenance {
    Provenance::native(
        Profile::TypeScript,
        ("0+unknown", &"0".repeat(64)),
        ("1.88.0", "1.88"),
    )
}

fn titles(facts: &Facts) -> Vec<&str> {
    facts.gaps.iter().map(|gap| gap.title.as_str()).collect()
}

#[test]
fn a_scope_of_only_test_sources_is_not_complete() {
    let tree = Tree::new(&[
        ("tsconfig.json", "{}"),
        ("src/a.test.ts", ""),
        ("src/tests/b.ts", ""),
    ]);
    let facts = collect(&request(&tree, true), provenance());
    assert!(facts.selected_files.is_empty());
    assert_eq!(titles(&facts), [NO_PRODUCTION_SOURCE]);
    let kept = collect(&request(&tree, false), provenance());
    assert_eq!(kept.selected_files, ["src/a.test.ts", "src/tests/b.ts"]);
    assert!(!titles(&kept).contains(&NO_PRODUCTION_SOURCE));
}

#[test]
fn a_production_file_beside_the_tests_removes_the_gap() {
    let tree = Tree::new(&[
        ("tsconfig.json", "{}"),
        ("src/a.ts", ""),
        ("src/a.test.ts", ""),
    ]);
    let facts = collect(&request(&tree, true), provenance());
    assert_eq!(facts.selected_files, ["src/a.ts"]);
    assert!(titles(&facts).is_empty());
}

// Consumer: a source file over the size limit. Its gap is UNKNOWN for that file only. The other
// files are still collected.
#[test]
fn a_source_over_the_size_limit_is_a_gap_and_the_others_are_collected() {
    let huge = "x".repeat(archkeel_snapshot::MAX_FILE_BYTES as usize + 1);
    let tree = Tree::new(&[
        ("tsconfig.json", "{}"),
        ("src/a.ts", ""),
        ("src/huge.ts", &huge),
    ]);
    let facts = collect(&request(&tree, false), provenance());

    // The file stays selected, as an unreadable file does; it has no file fact, only the gap.
    assert_eq!(facts.selected_files, ["src/a.ts", "src/huge.ts"]);
    assert_eq!(facts.files.len(), 1);
    assert_eq!(facts.files_read, 1);
    assert_eq!(
        titles(&facts),
        ["Source file over the size limit of 4194304 bytes: src/huge.ts"]
    );
}
