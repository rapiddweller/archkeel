// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Layout citation selection, separate from whole-run evaluation.

use archkeel_model::Reason;

#[test]
fn a_child_without_a_record_is_unknown_by_name() {
    let records = crate::layout::child_records([(7_usize, "a.b.m", "a.b")]);
    assert_eq!(crate::layout::cite("a.b", &records), Ok(7));
    assert_eq!(
        crate::layout::cite("a.c", &records),
        Err(Reason::UncitedChild("a.c".to_owned()))
    );
}

#[test]
fn a_module_of_the_same_name_as_a_package_is_the_cited_record() {
    // The first module of package `a.b` comes first; the module named `a.b` still wins.
    let records = crate::layout::child_records([
        (1_usize, "a.b.x", "a.b"),
        (2, "a.b.y", "a.b"),
        (3, "a.b", "a"),
    ]);
    assert_eq!(records.get("a.b"), Some(&3));
    let first = crate::layout::child_records([(1_usize, "a.b.x", "a.b"), (2, "a.b.y", "a.b")]);
    assert_eq!(first.get("a.b"), Some(&1));
}
