// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

use archkeel_snapshot::test_tree::Tree;

use super::*;

#[test]
fn the_source_digest_hashes_each_path_and_its_bytes_in_path_order() {
    let tree = Tree::new(&[("b.py", "b"), ("a.py", "a"), ("pyproject.toml", "[x]")]);
    let mut snapshot = Snapshot::new(&tree.path());
    let selected = ["b.py".to_owned(), "a.py".to_owned()];
    let (found, digest) = inputs(&mut snapshot, &selected);
    let paths: Vec<(&str, Role)> = found
        .iter()
        .map(|item| (item.path.as_str(), item.role))
        .collect();
    let expected = [
        ("a.py", Role::Selected),
        ("b.py", Role::Selected),
        ("pyproject.toml", Role::Resolution),
    ];
    assert_eq!(paths, expected);
    assert_eq!(found[0].digest, sha256_hex(b"a"));
    assert_eq!(
        digest,
        sha256_hex(b"a.py\0a\0b.py\0b\0pyproject.toml\0[x]\0")
    );
}
