// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the module tree and the crate discovery.

use super::*;

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
