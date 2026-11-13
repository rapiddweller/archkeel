// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

use super::*;
use crate::{test_tree::Tree, Snapshot};

#[test]
fn every_snapshot_read_is_checked_and_a_hit_discards_the_result() {
    let deep = "(".repeat(50_000);
    let tree = Tree::new(&[("first", "fact"), ("deep", &deep), ("last", "other")]);
    let result = bounded(|| {
        let mut snapshot = Snapshot::new(&tree.path());
        assert!(snapshot.read("first").is_some());
        assert!(snapshot.read("deep").is_none());
        assert!(snapshot.read("last").is_none());
        42
    });
    assert_eq!(
        result,
        Err(WorkLimit {
            path: "deep".into(),
            scope: WorkScope::File,
        })
    );
    assert!(Snapshot::new(&tree.path()).read("deep").is_some());
}

#[test]
fn charge_cannot_be_reset_by_quotes_comments_closers_or_word_runs() {
    for text in ["(", ")", "!", ".", "x ", "/* ", "\" ", "\u{e9}"] {
        assert!(over(text.repeat(50_000).as_bytes()), "{text}");
    }
    assert!(!over(&vec![b'a'; 4 << 20]));
}

#[test]
fn the_walked_read_cannot_bypass_the_charge() {
    let tree = Tree::new(&[("deep", &"(".repeat(50_000))]);
    let result = bounded(|| {
        let mut snapshot = Snapshot::new(&tree.path());
        assert_eq!(snapshot.check_root("."), crate::RootCheck::Contained);
        assert!(snapshot.read_walked("deep").is_none());
    });
    assert_eq!(result.unwrap_err().path, "deep");
}

#[test]
fn an_inner_boundary_cannot_hide_a_refusal_from_its_caller() {
    let result = bounded(|| {
        let _ = bounded(|| permits("deep", &vec![b'('; 50_000]));
        assert!(!permits("later", b"fact"));
    });
    assert_eq!(result.unwrap_err().path, "deep");
    assert_eq!(bounded(|| permits("next run", b"fact")), Ok(true));
}

#[test]
fn individually_accepted_reads_share_one_scan_budget() {
    let text = vec![b'a'; 1 << 20];
    assert!(!over(&text));
    let result = bounded(|| {
        for _ in 0..16 {
            assert!(bounded(|| permits("source", &text)).unwrap());
        }
        assert!(!permits("next", b"a"));
    });
    assert_eq!(result.unwrap_err().path, "next");
}

#[test]
fn the_exact_boundary_accepts_full_bytes_and_the_next_unit_refuses() {
    assert!(!exceeds(b"(x)", 9));
    assert!(exceeds(b"(x) ", 9));
    assert!(!over(b"import { x } from './other';"));
}
