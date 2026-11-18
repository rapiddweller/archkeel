// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the outside writer search of the Python collector (#1522). A file over the size limit
// of `read` is read in full, in order, and is an input with the digest of its whole text.

use crate::snapshot::digest;
use crate::test_tree::Tree;
use crate::{Snapshot, MAX_FILE_BYTES};

#[test]
fn a_large_file_is_read_in_full_and_digested_as_one_input() {
    let size = usize::try_from(MAX_FILE_BYTES).unwrap() + 100_003;
    let mut text = "x".repeat(size);
    text.push_str("\"app.lib\"");
    let tree = Tree::new(&[("vendor/big.c", text.as_str())]);
    let mut snapshot = Snapshot::new(&tree.path());
    assert!(snapshot.read("vendor/big.c").is_none());
    let mut seen = Vec::new();
    assert!(snapshot.read_parts("vendor/big.c", &mut |part| seen.extend_from_slice(part)));
    assert_eq!(seen, text.as_bytes());
    assert_eq!(
        snapshot.inputs(|_, digest, selected| (digest.to_owned(), selected)),
        [(digest(text.as_bytes()), false)]
    );
}

#[test]
fn a_second_read_preserves_selection_for_a_wire_record() {
    let tree = Tree::new(&[("source", "abc")]);
    let mut snapshot = Snapshot::new(&tree.path());
    assert!(snapshot.read("source").is_some());
    snapshot.select("source");
    assert!(snapshot.read("source").is_some());
    assert!(snapshot.read_parts("source", &mut |_| {}));
    assert_eq!(
        snapshot.inputs(|path, digest, selected| (path.to_owned(), digest.to_owned(), selected)),
        [(
            "source".to_owned(),
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad".to_owned(),
            true
        )]
    );
}

#[test]
fn an_absent_file_gives_no_part() {
    let tree = Tree::new(&[("a.c", "")]);
    let mut snapshot = Snapshot::new(&tree.path());
    let mut parts = 0;
    assert!(!snapshot.read_parts("b.c", &mut |_| parts += 1));
    assert_eq!(parts, 0);
    assert!(snapshot.inputs(|_, _, _| ()).is_empty());
}
