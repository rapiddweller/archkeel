// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

use serde_json::{json, Value};

use super::{answer, hex};
use crate::engine::tests::{golden_reply, NATIVE_CONTRACT};

fn request(reply: Option<&[u8]>, sections: &[&str]) -> Value {
    json!({
        "protocol": "archkeel-dual-run-2",
        "case": "c",
        "root": "/r",
        "config": "archkeel.toml",
        "baseline": null,
        "collector_argv": null,
        "pinned": false,
        "contracts": {"architecture-contract.json": NATIVE_CONTRACT},
        "reply": reply.map(|bytes| json!({"hex": bytes.iter().map(|b| format!("{b:02x}")).collect::<String>()})),
        "sections": sections,
        "namespace": "shop",
        "standard_library": [],
    })
}

fn frame(value: &Value) -> Value {
    let bytes = answer(value.to_string().as_bytes()).map_or(Vec::new(), |answered| answered.frame);
    serde_json::from_slice(&bytes).unwrap_or(Value::Null)
}

fn names_a_gap(value: &Value) -> bool {
    answer(value.to_string().as_bytes()).is_ok_and(|answered| answered.names_a_gap)
}

#[test]
fn the_frame_shows_what_the_core_read_and_decides_the_s1_kinds() {
    let reply = golden_reply();
    let got = frame(&request(
        Some(&reply),
        &["modules", "evidence", "violations"],
    ));
    // The native rule selects no module of the H-typescript reply: no receipt, so UNKNOWN.
    let unknown = json!({"NATIVE-ASSIGNMENT-COMPLETE": ["complete_assignment", "UNKNOWN"]});
    assert_eq!(got["rules"], unknown);
    assert_eq!(got["sections"], json!({"violations": []}));
    assert_eq!(
        got["unsupported"]["report"],
        "unsupported: the report payload: slice 0d ports it"
    );
    assert_eq!(
        got["self_test"]["contract"]["rules"]["NATIVE-NO-MODULE-CYCLES"],
        "no_component_cycles"
    );
    assert!(got["self_test"]["reply"]["files"].as_u64().unwrap_or(0) > 0);
    assert_eq!(
        got["unsupported"]["sections"]["modules"],
        "unsupported: section modules: slice S3 ports it"
    );
    let rules = got["unsupported"]["rules"]
        .as_object()
        .map_or(0, |rules| rules.len());
    assert_eq!(rules, 9);
}

#[test]
fn a_request_without_a_reply_says_so() {
    let got = frame(&request(None, &[]));
    assert!(got["self_test"]["reply"]["absent"].is_string());
    assert_eq!(got["unsupported"]["sections"], json!({}));
}

#[test]
fn a_wrong_protocol_an_unknown_field_or_an_unknown_section_is_refused() {
    let mut wrong = request(None, &[]);
    wrong["protocol"] = json!("other");
    assert!(answer(wrong.to_string().as_bytes()).is_err());
    let mut extra = request(None, &[]);
    extra["extra"] = json!(1);
    assert!(answer(extra.to_string().as_bytes()).is_err());
    let unknown = request(None, &["transitive_paths"]);
    let refused = answer(unknown.to_string().as_bytes());
    assert_eq!(
        refused.err().as_deref(),
        Some("unknown section transitive_paths")
    );
}

#[test]
fn hex_reads_bytes_and_refuses_bad_text() {
    assert_eq!(hex("00ff10"), Ok(vec![0, 255, 16]));
    assert!(hex("0").is_err());
    assert!(hex("zz").is_err());
}

#[test]
fn a_frame_with_an_unsupported_or_refused_part_names_a_gap() {
    let reply = golden_reply();
    assert!(names_a_gap(&request(Some(&reply), &["modules"])));
    let mut invalid = request(Some(&reply), &[]);
    invalid["contracts"] = json!({"architecture-contract.json": "not a contract"});
    assert!(names_a_gap(&invalid));
    assert!(frame(&invalid)["self_test"]["contract"]["refused"].is_string());
    let truncated = request(Some(&reply[..reply.len() / 2]), &[]);
    assert!(names_a_gap(&truncated));
    assert!(frame(&truncated)["self_test"]["reply"]["refused"].is_string());
}

#[test]
fn a_request_with_a_baseline_is_refused_by_name() {
    let reply = golden_reply();
    let mut with_baseline = request(Some(&reply), &["violations"]);
    with_baseline["baseline"] = json!("baseline.json");
    assert!(names_a_gap(&with_baseline));
    let got = frame(&with_baseline);
    assert_eq!(got["rules"], json!({}));
    assert_eq!(
        got["unsupported"]["rules"],
        "unsupported: the baseline of the request: no slice reads it yet"
    );
}
