// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the coverage gaps of the reply. A part of the tree that the collector cannot read
// must be visible as a problem, so that the collection is never complete by omission.

use super::*;
use crate::test_tree::Tree;

#[cfg(unix)]
#[test]
fn an_unreadable_directory_is_a_problem() {
    use std::os::unix::fs::PermissionsExt;

    let tree = Tree::new(&[("src/open/a.ts", ""), ("src/locked/b.ts", "")]);
    let locked = tree.root.join("src/locked");
    fs::set_permissions(&locked, fs::Permissions::from_mode(0o000)).unwrap();
    // A superuser can read the directory anyway, so the case does not exist for it.
    let readable = fs::read_dir(&locked).is_ok();
    let mut snapshot = Snapshot::new(&tree.path());
    let (_, directories) = snapshot.entries("src");
    let (files, _) = snapshot.entries("src/locked");
    fs::set_permissions(&locked, fs::Permissions::from_mode(0o755)).unwrap();
    if readable {
        eprintln!("skipped: the superuser can read a directory with mode 000");
        return;
    }
    assert_eq!(directories, ["locked", "open"]);
    assert!(files.is_empty());
    let problems: Vec<&String> = snapshot.problems.iter().collect();
    assert_eq!(problems, ["Unreadable source directory: src/locked"]);
}

#[cfg(target_os = "linux")]
#[test]
fn a_name_that_is_not_utf8_is_a_problem() {
    use std::ffi::OsStr;
    use std::os::unix::ffi::OsStrExt;

    let tree = Tree::new(&[("src/a.ts", "")]);
    fs::write(
        tree.root.join("src").join(OsStr::from_bytes(b"b\xff.ts")),
        "",
    )
    .unwrap();
    let mut snapshot = Snapshot::new(&tree.path());
    let (files, _) = snapshot.entries("src");
    assert_eq!(files, ["a.ts"]);
    let problems: Vec<&String> = snapshot.problems.iter().collect();
    assert_eq!(problems, ["Source name is not UTF-8: src/b\u{fffd}.ts"]);
}

// Consumer: the bound on one file read. A file over the limit is never held in memory, and the
// collection names it, so the collection is never complete by omission.

#[test]
fn a_file_over_the_size_limit_is_not_read() {
    let at_limit = "a".repeat(MAX_FILE_BYTES as usize);
    let over_limit = "a".repeat(MAX_FILE_BYTES as usize + 1);
    let tree = Tree::new(&[("src/at.ts", &at_limit), ("src/over.ts", &over_limit)]);
    let mut snapshot = Snapshot::new(&tree.path());

    assert_eq!(
        snapshot.read("src/at.ts").map(|raw| raw.len()),
        Some(at_limit.len())
    );
    assert_eq!(snapshot.read("src/over.ts"), None);
    assert_eq!(
        snapshot.size_gap("src/over.ts").as_deref(),
        Some("Source file over the size limit of 4194304 bytes: src/over.ts")
    );
    assert_eq!(snapshot.size_gap("src/at.ts"), None);
    let inputs: Vec<String> = snapshot
        .inputs()
        .into_iter()
        .map(|input| input.path)
        .collect();
    assert_eq!(inputs, ["src/at.ts"]);
}

#[test]
fn a_file_over_the_size_limit_is_refused_once_and_then_at_once() {
    let over_limit = "a".repeat(MAX_FILE_BYTES as usize + 1);
    let tree = Tree::new(&[("src/over.ts", &over_limit), ("src/ok.ts", "x")]);
    let mut snapshot = Snapshot::new(&tree.path());
    assert!(!snapshot.readable("src/over.ts"));
    // The file is now known as too large: a second question reads nothing.
    std::fs::remove_file(tree.root.join("src/over.ts")).unwrap();
    assert!(!snapshot.readable("src/over.ts"));
    assert!(snapshot.size_gap("src/over.ts").is_some());
    assert!(snapshot.readable("src/ok.ts") && snapshot.readable("src/ok.ts"));
}
