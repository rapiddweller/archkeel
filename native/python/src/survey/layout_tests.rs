// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the scan receipt reads the module files under the roots (AD-450). A file that the
// parent rule cannot place, a module that two files give, and a module file that the survey cannot
// read must each be a gap.

use super::*;
use crate::survey::targets::tests::{reasons, surveyed, surveyed_at, surveyed_in};

#[test]
fn a_module_of_two_files_is_a_gap_for_each_and_no_module() {
    let found = surveyed_in(
        &[
            ("src/app/__init__.py", ""),
            ("src/app/service.py", ""),
            ("lib/app/service.py", ""),
        ],
        &["src", "lib"],
        "app",
    );
    let gaps = reasons(&found);
    assert_eq!(gaps.len(), 2, "{gaps:?}");
    assert!(
        gaps.iter().all(|gap| gap.starts_with(DUPLICATE)),
        "{gaps:?}"
    );
    let modules: Vec<&str> = found
        .files
        .iter()
        .map(|file| file.module.as_str())
        .collect();
    assert_eq!(modules, ["app"]);
}

#[test]
fn a_top_package_above_its_root_is_a_gap_and_a_root_that_is_the_package_is_not() {
    let above = surveyed_in(
        &[("src/app/inner/app/deep.py", "")],
        &["src/app/inner"],
        "app",
    );
    assert!(
        reasons(&above)[0].starts_with(OUTSIDE_LAYOUT),
        "{:?}",
        reasons(&above)
    );
    for (roots, files) in [
        (
            ["demo"],
            [("demo/__init__.py", ""), ("demo/sub/__init__.py", "")],
        ),
        (["."], [("demo/__init__.py", ""), ("demo/x.py", "")]),
        (
            ["src"],
            [("src/demo/__init__.py", ""), ("src/demo/x.py", "")],
        ),
    ] {
        let found = surveyed_in(&files, &roots, "demo");
        assert!(
            found.unknowns.is_empty(),
            "{roots:?}: {:?}",
            reasons(&found)
        );
    }
}

#[test]
fn a_stub_or_compiled_module_file_is_a_gap_and_a_cached_one_is_not() {
    for name in ["client.pyi", "fast.so", "fast.pyd", "old.pyc", "window.pyw"] {
        let file = format!("src/app/{name}");
        let found = surveyed(&[("src/app/__init__.py", ""), (&file, "")]);
        assert_eq!(reasons(&found), [format!("{FOREIGN}: {file}")]);
    }
    // A stub beside its source module is no gap; a stub of a package beside `__init__.py` too.
    let pairs = [
        ("src/app/client.pyi", "src/app/client.py"),
        ("src/app/__init__.pyi", "src/app/__init__.py"),
    ];
    for (stub, source) in pairs {
        let found = surveyed(&[
            ("src/app/__init__.py", ""),
            (source, ""),
            (stub, "x: int\n"),
        ]);
        assert!(found.unknowns.is_empty(), "{stub}: {:?}", reasons(&found));
    }
    let compiled = surveyed(&[
        ("src/app/__init__.py", ""),
        ("src/app/fast.py", ""),
        ("src/app/fast.so", ""),
    ]);
    assert_eq!(reasons(&compiled), [format!("{FOREIGN}: src/app/fast.so")]);
    let cached = surveyed(&[
        ("src/app/__init__.py", ""),
        ("src/app/__pycache__/x.pyc", ""),
    ]);
    assert!(cached.unknowns.is_empty(), "{:?}", reasons(&cached));
}

#[cfg(unix)]
#[test]
fn an_unreadable_directory_is_a_gap() {
    use std::os::unix::fs::PermissionsExt;

    let tree = archkeel_snapshot::test_tree::Tree::new(&[
        ("src/app/__init__.py", ""),
        ("src/app/locked/hidden.py", ""),
    ]);
    let locked = tree.root.join("src/app/locked");
    std::fs::set_permissions(&locked, std::fs::Permissions::from_mode(0o000)).unwrap();
    let readable = std::fs::read_dir(&locked).is_ok();
    let mut snapshot = archkeel_snapshot::Snapshot::new(&tree.path());
    let scope = crate::discover::scope(&mut snapshot, &["src".to_owned()], false);
    std::fs::set_permissions(&locked, std::fs::Permissions::from_mode(0o755)).unwrap();
    if readable {
        eprintln!("skipped: the superuser can read a directory with mode 000");
        return;
    }
    assert_eq!(scope.selected, ["src/app/__init__.py"]);
    std::fs::set_permissions(&locked, std::fs::Permissions::from_mode(0o000)).unwrap();
    let found = surveyed_at(&tree);
    std::fs::set_permissions(&locked, std::fs::Permissions::from_mode(0o755)).unwrap();
    let wanted = format!("{UNREADABLE}: Unreadable source directory: src/app/locked");
    assert!(reasons(&found).contains(&wanted), "{:?}", reasons(&found));
    let gaps: Vec<String> = problems(&snapshot.problems)
        .iter()
        .map(|gap| gap.title.clone())
        .collect();
    assert_eq!(
        gaps,
        [format!(
            "{UNREADABLE}: Unreadable source directory: src/app/locked"
        )]
    );
}

#[cfg(unix)]
#[test]
fn a_linked_directory_below_a_root_is_a_gap() {
    let tree = archkeel_snapshot::test_tree::Tree::new(&[
        ("src/app/__init__.py", ""),
        ("src/app/client/__init__.py", ""),
        ("elsewhere/sub/__init__.py", "import app.service\n"),
    ]);
    std::os::unix::fs::symlink(
        "../../../elsewhere/sub",
        tree.root.join("src/app/client/sub"),
    )
    .unwrap();
    let found = surveyed_at(&tree);
    assert!(
        reasons(&found).contains(&format!("{LINKED}: src/app/client/sub")),
        "{:?}",
        reasons(&found)
    );
}

/// Each `.py` file below the root that an independent walk finds, outside `__pycache__`.
fn walked(root: &std::path::Path, base: &std::path::Path, found: &mut Vec<String>) {
    for entry in std::fs::read_dir(root).unwrap() {
        let path = entry.unwrap().path();
        let rel = path
            .strip_prefix(base)
            .unwrap()
            .to_str()
            .unwrap()
            .to_owned();
        if path.is_dir() && !rel.ends_with("__pycache__") {
            walked(&path, base, found);
        } else if rel.ends_with(".py") && !rel.contains("__pycache__") {
            found.push(rel);
        }
    }
}

#[test]
fn the_survey_selects_each_source_file_that_an_independent_walk_finds() {
    let tree = archkeel_snapshot::test_tree::Tree::new(&[
        ("src/app/__init__.py", ""),
        ("src/app/a/b/c/deep.py", ""),
        ("src/app/.hidden/inner.py", ""),
        ("src/app/data.txt", ""),
        ("src/app/__pycache__/cached.py", ""),
        ("src/app/tests/test_x.py", ""),
    ]);
    let mut expected = Vec::new();
    walked(&tree.root.join("src"), &tree.root, &mut expected);
    expected.sort();
    let mut selected = surveyed_at(&tree).coverage.selected_files;
    selected.sort();
    assert_eq!(selected, expected);
}

#[test]
fn a_file_with_an_encoding_declaration_other_than_utf8_is_a_gap() {
    let found = surveyed(&[
        ("src/app/__init__.py", ""),
        ("src/app/a.py", "# coding: utf-7\nimport os\n"),
    ]);
    let messages: Vec<String> = found
        .unknowns
        .iter()
        .filter_map(|gap| match &gap.data {
            GapFact::ExceptionGap { data, .. } => data.message.clone(),
            _ => None,
        })
        .collect();
    assert_eq!(
        messages,
        ["source_encoding: the file declares the encoding utf-7"]
    );
    assert_eq!(found.files.len(), 1);
}
