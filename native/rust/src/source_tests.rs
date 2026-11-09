// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the walk of the collector. Each test builds a small tree in a temporary directory.

use super::*;
use crate::test_tree::tree;

#[test]
fn walks_sorted_files_and_skips_target_and_hidden_directories() {
    let root = tree(
        "walk",
        &[
            ("b.rs", ""),
            ("a/x.rs", ""),
            ("target/t.rs", ""),
            (".hidden/h.rs", ""),
            ("a/y.txt", ""),
        ],
    );
    let source = Source::new(root.to_str().unwrap());
    assert_eq!(source.walk(""), ["a/x.rs", "a/y.txt", "b.rs"]);
    assert_eq!(source.walk("a"), ["a/x.rs", "a/y.txt"]);
    let _ = fs::remove_dir_all(root);
}

#[test]
fn a_read_is_digested_and_a_selected_read_wins_over_a_resolution_read() {
    let root = tree("read", &[("a.rs", "fn a() {}")]);
    let mut source = Source::new(root.to_str().unwrap());
    source.read("a.rs", Role::Resolution).unwrap();
    source.read("a.rs", Role::Selected).unwrap();
    let inputs = source.inputs();
    assert_eq!(inputs.len(), 1);
    assert_eq!(inputs[0].role, Role::Selected);
    assert_eq!(inputs[0].digest, sha256_hex(b"fn a() {}"));
    let _ = fs::remove_dir_all(root);
}

#[test]
fn a_file_over_the_limit_and_a_missing_file_give_a_reason_that_names_them() {
    let root = tree("limit", &[]);
    let big = root.join("big.rs");
    fs::create_dir_all(&root).unwrap();
    File::create(&big)
        .unwrap()
        .set_len(MAX_FILE_BYTES + 1)
        .unwrap();
    let mut source = Source::new(root.to_str().unwrap());
    assert_eq!(
        source.read("big.rs", Role::Selected).unwrap_err(),
        format!("File is larger than {MAX_FILE_BYTES} bytes: big.rs")
    );
    assert_eq!(
        source.read("none.rs", Role::Selected).unwrap_err(),
        "Unreadable file: none.rs"
    );
    assert!(source.inputs().is_empty());
    let _ = fs::remove_dir_all(root);
}

#[cfg(unix)]
#[test]
fn a_symbolic_link_is_neither_read_nor_entered() {
    let root = tree("link", &[("real.rs", "x"), ("dir/in.rs", "x")]);
    std::os::unix::fs::symlink(root.join("real.rs"), root.join("link.rs")).unwrap();
    std::os::unix::fs::symlink(root.join("dir"), root.join("linkdir")).unwrap();
    let mut source = Source::new(root.to_str().unwrap());
    assert_eq!(
        source.read("link.rs", Role::Selected).unwrap_err(),
        "A symbolic link is not read: link.rs"
    );
    assert!(!source.is_file("link.rs") && !source.is_dir("linkdir"));
    assert_eq!(source.walk(""), ["dir/in.rs", "real.rs"]);
    let _ = fs::remove_dir_all(root);
}
