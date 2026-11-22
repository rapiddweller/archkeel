// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// The premises of the contract on the page (AD-664, #1549): a PASS that rests on one is never a
// bare PASS.

use super::*;

// #1549: a PASS that holds because of a stated external user reads like one under a trojan horse reach:
// the badge, the title, the note and the list of the rules name the premise and the entry.
#[test]
fn a_page_names_each_pass_under_a_stated_external_user() {
    let frame = json!({"status": "PASS", "scope": "complete",
        "rules": {"U": ["unused_public", "PASS"], "L": ["root_layout", "PASS"]},
        "premises": {"U": [{"kind": "external_user", "subject": "app.api:serve"}]},
        "assuming": "1 stated external user"});
    let page = document(&frame);
    assert!(
        page.contains("PASS under 1 stated external user</span>"),
        "{page}"
    );
    assert!(page.contains("All 2 rules hold; 1 hold under 1 stated external user"));
    assert!(page.contains("PASS under 1 stated external user: 1 rule holds only under"));
    assert!(page.contains("PASS UNDER 1 STATED EXTERNAL USER"));
    assert!(page.contains("app.api:serve"));
    let plain = page.split("PASS UNDER").next().unwrap_or_default();
    assert!(
        !plain.contains("<span class=\"rp-code\">U</span>"),
        "U is no plain PASS"
    );
    // A run with no stated premise keeps the bare word.
    let bare = document(&json!({"status": "PASS", "scope": "complete",
        "rules": {"L": ["root_layout", "PASS"]}}));
    assert!(!bare.contains("assuming") && bare.contains(">PASS</span>"));
}
