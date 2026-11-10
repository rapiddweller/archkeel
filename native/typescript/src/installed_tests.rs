// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: file selection, which skips an installed package.

use super::*;
use archkeel_snapshot::test_tree::Tree;

#[test]
fn a_path_below_node_modules_is_installed() {
    let tree = Tree::new(&[("node_modules/a/index.ts", ""), ("src/b.ts", "")]);
    let mut snapshot = Snapshot::new(&tree.path());
    assert!(installed(&mut snapshot, "node_modules/a/index.ts"));
    assert!(!installed(&mut snapshot, "src/b.ts"));
}

#[test]
fn a_name_that_only_contains_node_modules_is_not_installed() {
    let tree = Tree::new(&[("src/my_node_modules/c.ts", "")]);
    let mut snapshot = Snapshot::new(&tree.path());
    assert!(!installed(&mut snapshot, "src/my_node_modules/c.ts"));
}

#[cfg(unix)]
#[test]
fn a_link_into_an_installed_package_is_installed() {
    let tree = Tree::new(&[("node_modules/p/lib.ts", "")]);
    std::os::unix::fs::symlink(tree.root.join("node_modules/p"), tree.root.join("vendor")).unwrap();
    let mut snapshot = Snapshot::new(&tree.path());
    assert!(installed(&mut snapshot, "vendor/lib.ts"));
}
