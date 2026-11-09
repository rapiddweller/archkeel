// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the module tree and the crate discovery.

use super::*;

#[test]
fn dirname_and_join_keep_the_snapshot_root_as_the_empty_directory() {
    assert_eq!(dirname("a/b/c.rs"), "a/b");
    assert_eq!(dirname("c.rs"), "");
    assert_eq!(join("", "c.rs"), "c.rs");
    assert_eq!(join(".", "c.rs"), "c.rs");
    assert_eq!(join("a", "../c.rs"), "a/../c.rs");
}

#[test]
fn normalize_removes_dots_and_refuses_to_leave_the_snapshot() {
    assert_eq!(normalize("a/./b/../c.rs").as_deref(), Some("a/c.rs"));
    for path in [
        "../x.rs",
        "a/../../x.rs",
        "/etc/passwd",
        "a\\b.rs",
        "",
        ".",
        "a\0b",
    ] {
        assert_eq!(normalize(path), None, "{path:?}");
    }
}
