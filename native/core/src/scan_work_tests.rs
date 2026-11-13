// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! A parse-work refusal writes no frame, even after another file gave facts.

use super::tests::{repository, request};

#[test]
fn a_parse_work_refusal_is_exit_two_without_frame_bytes() {
    let root = repository("parse-work");
    let text = format!("{}0{};", "(".repeat(50_000), ")".repeat(50_000));
    std::fs::write(root.join("src/deep.ts"), text).unwrap();
    let mut out = Vec::new();
    let (code, reason) = crate::respond_with(
        super::answer,
        request(&root).to_string().as_bytes(),
        &mut out,
    );
    assert_eq!(code, 2, "{reason:?}");
    let reason: serde_json::Value = serde_json::from_str(&reason.unwrap().to_string()).unwrap();
    assert_eq!(reason["kind"], "parse_work_limit");
    assert!(out.is_empty());
}
