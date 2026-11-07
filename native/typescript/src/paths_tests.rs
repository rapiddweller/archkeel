// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: file discovery, which must select the same files as `config._discover`.

use super::*;

#[test]
fn normpath_and_join_follow_posixpath() {
    let cases = [
        ("", "."),
        ("a/./b//c/", "a/b/c"),
        ("../a/../../b", "../../b"),
        ("/../a", "/a"),
        ("//a", "//a"),
        ("///a", "/a"),
        ("a/..", "."),
    ];
    for (path, expected) in cases {
        assert_eq!(normpath(path), expected, "{path}");
    }
    assert_eq!(join(".", "src"), "src");
    assert_eq!(join("/", "src"), "/src");
    assert_eq!(join("sub", "/abs"), "/abs");
    assert_eq!(join("sub", "../x"), "x");
}

#[test]
fn dirname_and_basename_follow_posixpath() {
    assert_eq!(dirname("tsconfig.json"), "");
    assert_eq!(dirname("a/b/c.ts"), "a/b");
    assert_eq!(dirname("/x"), "/");
    assert_eq!(basename("a/b/c.ts"), "c.ts");
}

#[test]
fn scope_tests_follow_config_within() {
    assert!(within(".", "src/a.ts"));
    assert!(within("src", "src/a.ts"));
    assert!(!within("src", "srcx/a.ts"));
    assert!(!within("/", "/src"));
    assert!(is_outside("../a") && is_outside(".."));
    assert!(!is_outside("..a"));
}

#[test]
fn the_longest_suffix_decides_the_source_kind() {
    assert_eq!(
        suffix("a.d.ts"),
        Some((".d.ts", Some(SourceKind::Declaration)))
    );
    assert_eq!(
        suffix("a.tsx"),
        Some((".tsx", Some(SourceKind::TypeScript)))
    );
    assert_eq!(
        suffix("a.mjs"),
        Some((".mjs", Some(SourceKind::JavaScript)))
    );
    assert_eq!(suffix("a.json"), Some((".json", None)));
    assert_eq!(suffix("a.css"), None);
}

#[test]
fn a_higher_priority_sibling_shadows_a_file() {
    let known = |path: &str| ["a.ts", "a.js", "a.d.ts", "b.d.ts", "b.js", "c.mts"].contains(&path);
    assert!(shadowed("a.js", &known));
    assert!(shadowed("a.d.ts", &known));
    assert!(!shadowed("a.ts", &known));
    // A declaration does not shadow its JavaScript file.
    assert!(!shadowed("b.js", &known));
    assert!(!shadowed("c.mts", &known));
}
