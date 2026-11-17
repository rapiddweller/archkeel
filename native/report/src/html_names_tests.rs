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

// #1616: gaps of one hygiene family that differ only in what they point at are one card.
#[test]
fn near_identical_hygiene_gaps_are_one_card_with_a_list() {
    let mut named = serde_json::Map::new();
    for n in 0..9 {
        named.insert(
            format!("hygiene:responsibility.missing:{n}"),
            json!(format!(
                "contract hygiene responsibility.missing: contract.json/components/{n}/responsibilities part{n}: The architect-decided component has no substantive responsibility."
            )),
        );
    }
    named.insert(
        "hygiene:decision.open:1".to_owned(),
        json!("contract hygiene decision.open: contract.json/decisions/0 alpha: The contract has an open decision."),
    );
    let page = document(&json!({"status": "UNKNOWN", "unsupported": {"rules": named}}));
    assert!(page.contains("9 components have no written responsibility"));
    assert!(page.contains("Which: 9"));
    assert!(page.contains("contract.json/components/8/responsibilities part8"));
    // the family card, the decision card and the card of the open run
    assert_eq!(page.matches("<article class=\"rp-cause\">").count(), 3);
    // one decision stays a plain card with its own reason
    assert!(page.contains("contract hygiene decision.open"));
}
