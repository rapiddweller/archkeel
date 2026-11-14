// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the scan receipt reads the module files under the roots (AD-450). A file that the
// parent rule cannot place, a module that two files give, and a module file that the survey cannot
// read must each be a gap.

use super::*;
use crate::survey::targets::tests::{reasons, surveyed, surveyed_in};

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
    for name in ["client.pyi", "fast.so", "fast.pyd", "old.pyc"] {
        let file = format!("src/app/{name}");
        let found = surveyed(&[("src/app/__init__.py", ""), (&file, "")]);
        assert_eq!(reasons(&found), [format!("{FOREIGN}: {file}")]);
    }
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
