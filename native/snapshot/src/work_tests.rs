// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

use super::*;
use crate::{test_tree::Tree, Snapshot};

fn permits(path: &str, bytes: &[u8]) -> bool {
    super::permits(std::path::Path::new(""), path, bytes)
}

#[test]
fn repeated_reads_of_one_path_do_not_spend_the_retained_input_budget_again() {
    let text = "x".repeat(1 << 20);
    let tree = Tree::new(&[("source", &text)]);
    let result = bounded(|| {
        let mut snapshot = Snapshot::new(&tree.path());
        for _ in 0..65 {
            assert!(snapshot.read("source").is_some());
        }
        assert_eq!(charged_bytes(), Some(text.len() as u64));
        assert_eq!(read_bytes(), Some(65 * text.len() as u64));
    });
    assert_eq!(result, Ok(()));
}

#[test]
fn normalized_paths_count_once_but_other_roots_and_growth_still_spend_bytes() {
    assert_eq!(
        bounded(|| {
            let a = std::path::Path::new("a");
            let b = std::path::Path::new("b");
            assert!(super::permits(a, "./source", b"123"));
            assert!(super::permits(a, "source", b"123"));
            assert_eq!(charged_bytes(), Some(3));
            assert!(super::permits(b, "source", b"123"));
            assert!(super::permits(a, "source", b"12345"));
            assert_eq!(charged_bytes(), Some(8));
        }),
        Ok(())
    );
}

#[cfg(unix)]
#[test]
fn distinct_source_aliases_keep_their_own_retained_input_charge() {
    let tree = Tree::new(&[("source", "fact")]);
    std::os::unix::fs::symlink("source", std::path::Path::new(&tree.path()).join("alias")).unwrap();
    assert_eq!(
        bounded(|| {
            let mut snapshot = Snapshot::new(&tree.path());
            assert!(snapshot.read("source").is_some());
            assert!(snapshot.read("alias").is_some());
            assert_eq!(charged_bytes(), Some(8));
        }),
        Ok(())
    );
}

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
fn every_byte_and_token_counts_once_not_once_per_later_byte() {
    for text in ["(", ")", "!", ".", "x ", "/* ", "\" ", "\u{e9}"] {
        let text = text.repeat((crate::MAX_FILE_BYTES as usize) / text.len());
        assert!(!over(text.as_bytes()));
    }
    assert!(!over(&vec![b'a'; 4 << 20]));
}

#[test]
fn a_flat_four_mib_expression_fits_the_linear_and_bracket_bounds() {
    let term = "\"a\" + ";
    let suffix = "\"a\";\n";
    let size = crate::MAX_FILE_BYTES as usize - 1;
    let count = (size - suffix.len()) / term.len();
    let mut text = format!("{}{suffix}", term.repeat(count));
    text.push_str(&" ".repeat(size - text.len()));
    assert_eq!(text.len(), size);
    assert_eq!(bounded(|| permits("source", text.as_bytes())), Ok(true));
}

#[test]
fn actual_nesting_is_separate_from_file_width_and_literal_text() {
    let deep = "(".repeat(MAX_NESTING + 1);
    for wrapped in [
        deep.clone(),
        format!("`text ${{{deep}0}}`"),
        format!("[{{{deep}"),
        format!("/* outer /* () */ tail */ {deep}"),
    ] {
        assert!(crate::nesting::over(wrapped.as_bytes(), MAX_NESTING));
    }
    for literal in [
        format!("/*{deep}*/"),
        format!("/* outer /*{deep}*/ {deep}*/"),
        format!("/*{deep}"),
        format!("/*{deep}/"),
        format!("/*{deep}*"),
        format!("\"{deep}\""),
        format!("'{deep}'"),
        format!("`{deep}`"),
        format!("r##\"text \"{deep}\"##"),
        format!("br##\"text \"{deep}\"##"),
    ] {
        assert!(!crate::nesting::over(literal.as_bytes(), MAX_NESTING));
    }
    assert!(crate::nesting::over(
        format!("fn f<'a>() {{ {deep}").as_bytes(),
        MAX_NESTING
    ));
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
        for index in 0..MAX_SCAN_BYTES / text.len() as u64 {
            assert!(bounded(|| permits(&format!("source{index}"), &text)).unwrap());
        }
        assert!(!permits("next", b"a"));
    });
    assert_eq!(result.unwrap_err().path, "next");
}

#[test]
fn concurrent_threads_do_not_share_or_reset_each_others_budget() {
    let barrier = std::sync::Barrier::new(2);
    std::thread::scope(|scope| {
        let refused = scope.spawn(|| {
            bounded(|| {
                assert!(!permits("deep", &vec![b'('; 50_000]));
                barrier.wait();
                barrier.wait();
                assert!(!permits("after", b"fact"));
            })
        });
        barrier.wait();
        assert_eq!(bounded(|| permits("other", b"fact")), Ok(true));
        barrier.wait();
        assert_eq!(refused.join().unwrap().unwrap_err().path, "deep");
    });
}

#[test]
fn the_exact_boundary_accepts_full_bytes_and_the_next_unit_refuses() {
    assert!(!exceeds(b"(x)", 6));
    assert!(exceeds(b"(x) ", 6));
    assert!(!over(b"import { x } from './other';"));
}

#[test]
fn shared_block_comment_end_keeps_nested_and_truncated_bounds() {
    assert_eq!(crate::block_comment_end(b"/* /* */ */tail", 0), 11);
    assert_eq!(crate::block_comment_end(b"/* /* */", 0), 8);
    assert_eq!(crate::block_comment_end(b"/* */", usize::MAX), 5);
}
