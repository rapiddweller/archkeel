// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: Explore with a 9.0.0 request (AD-313). A scope that holds only test sources must not
// read as a complete scan of zero files.

use archkeel_wire::protocol::Version;
use serde_json::Value;

use super::*;
use crate::test_tree::Tree;

fn request(tree: &Tree, exclude_test_sources: bool) -> Request {
    Request {
        version: Version::V9,
        root: tree.path(),
        git_head: "a".repeat(40),
        dirty: Value::Bool(false),
        roots: vec!["src".to_owned()],
        namespace: "shop".to_owned(),
        exclude_test_sources,
        tsconfig: "tsconfig.json".to_owned(),
        bundler: false,
    }
}

fn provenance() -> Provenance {
    Provenance {
        profile: PROFILE,
        adapter_version: "0+unknown".to_owned(),
        code_digest: "0".repeat(64),
        runtime_name: "rust",
        runtime_version: "1.88.0".to_owned(),
        runtime_required: ">=1.88".to_owned(),
    }
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
    assert_eq!(titles(&facts), [imports::GLOBALS_UNEXAMINED]);
}

// Consumer: a source file over the size limit. Its gap is UNKNOWN for that file only. The other
// files are still collected.
#[test]
fn a_source_over_the_size_limit_is_a_gap_and_the_others_are_collected() {
    let huge = "x".repeat(crate::snapshot::MAX_FILE_BYTES as usize + 1);
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
        [
            "Source file over the size limit of 4194304 bytes: src/huge.ts",
            IMPORT_GAP
        ]
    );
}
