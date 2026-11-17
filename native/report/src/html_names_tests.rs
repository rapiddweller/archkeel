// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// The names of modules on the page (#1617).

use super::*;

#[test]
fn a_module_identity_is_shown_with_its_real_characters_and_the_text_stays_escaped() {
    // #1617: the collector writes `.` and `_` of a path as `_x2e_` and `_x5f_`.
    let frame = json!({"status": "UNKNOWN", "rules": {"R": ["rule", "UNKNOWN"]},
        "explained": {"R": "gap at web.src.index_x2e_ts and web.src._x5f__x5f_tests_x5f__x5f_ <b>"}});
    let page = document(&frame);
    assert!(page.contains("web.src.index.ts and web.src.__tests__ &lt;b&gt;"));
    assert!(!page.contains("_x2e_") && !page.contains("_x5f_"));
}
