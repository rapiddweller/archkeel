// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

use serde_json::{json, Value};

use super::{answer, hex};
use crate::engine::tests::{golden_profile, golden_reply, NATIVE_CONTRACT};

fn request(reply: Option<&[u8]>, sections: &[&str]) -> Value {
    json!({
        "protocol": "archkeel-dual-run-3",
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
        "profile": golden_profile(),
        "standard_library": [],
        "insides": [],
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
        &["metrics", "evidence", "violations"],
    ));
    // The native rules select no module of the H-typescript reply: the subject check of the
    // reference engine fails, so the scope is not complete and each decided rule is UNKNOWN
    // with its reason (AD-378).
    let decided = got["rules"].as_object().cloned().unwrap_or_default();
    assert_eq!(decided.len(), 7);
    assert!(decided.values().all(|value| value[1] == "UNKNOWN"));
    assert_eq!(
        got["explained"]["NATIVE-EXTERNAL-SYN"],
        "incomplete scope: the rule NATIVE-ASSIGNMENT-COMPLETE selects no module"
    );
    assert_eq!(got["status"], "UNKNOWN");
    assert_eq!(got["violations"], json!({}));
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
        got["unsupported"]["sections"]["metrics"],
        "unsupported: section metrics: slice S10 ports it"
    );
    let rules = got["unsupported"]["rules"]
        .as_object()
        .map_or(0, |rules| rules.len());
    assert_eq!(rules, 3);
}

#[test]
fn a_reply_of_an_unpinned_external_collector_gives_no_pass() {
    let reply = golden_reply();
    let mut external = request(Some(&reply), &[]);
    external["collector_argv"] = json!(["collector"]);
    let got = frame(&external);
    let why = "incomplete scope: the reply comes from an external collector without a pin";
    // The native rules also select no module; the producer comes first in the proof.
    assert_eq!(got["explained"]["NATIVE-EXTERNAL-SYN"], why);
    external["pinned"] = json!(true);
    let pinned = frame(&external);
    assert_ne!(pinned["explained"]["NATIVE-EXTERNAL-SYN"], why);
}

#[test]
fn a_collector_argv_above_its_limit_is_refused_by_name() {
    let mut long = request(None, &[]);
    long["collector_argv"] = json!(vec!["x"; 65]);
    long["pinned"] = json!(true);
    let error = answer(long.to_string().as_bytes())
        .err()
        .unwrap_or_default();
    assert_eq!(error, "c: collector_argv has more than 64 entries");
    long["collector_argv"] = json!(vec!["x"; 64]);
    assert!(answer(long.to_string().as_bytes()).is_ok());
}

#[test]
fn a_frame_without_rules_passes_only_with_a_complete_scope() {
    // L-35b: zero decided rules give PASS only for a contract without rules and a complete
    // scope, as `inspect_observation` gives (`check/run.py:76`).
    let reply = golden_reply();
    let mut empty = request(Some(&reply), &[]);
    let contract = r#"{"schema_version": "2.2.0", "components": [], "rules": []}"#;
    empty["contracts"] = json!({"architecture-contract.json": contract});
    let got = frame(&empty);
    assert_eq!(
        (got["status"].clone(), got["scope"].clone()),
        (json!("PASS"), json!("complete"))
    );
    empty["collector_argv"] = json!(["collector"]);
    let got = frame(&empty);
    assert_eq!(got["status"], "UNKNOWN");
    assert_eq!(
        got["scope"],
        "incomplete scope: the reply comes from an external collector without a pin"
    );
    let mut absent = request(None, &[]);
    absent["contracts"] = json!({"architecture-contract.json": contract});
    assert_eq!(frame(&absent)["status"], "UNKNOWN");
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
    let repeated = request(None, &["modules", "violations", "modules"]);
    let refused = answer(repeated.to_string().as_bytes()).err();
    assert_eq!(
        refused.as_deref(),
        Some("repeated section modules: name each section one time")
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

#[test]
fn a_request_of_another_protocol_is_refused_by_its_protocol_name() {
    let mut old = request(None, &["violations"]);
    old["protocol"] = json!("archkeel-dual-run-1");
    if let Some(fields) = old.as_object_mut() {
        fields.remove("namespace");
        fields.remove("profile");
        fields.remove("standard_library");
    }
    let refused = answer(old.to_string().as_bytes()).err();
    assert_eq!(
        refused.as_deref(),
        Some("unknown protocol archkeel-dual-run-1")
    );
}

#[test]
fn settings_of_another_profile_are_refused_by_name_and_give_no_edges() {
    let reply = golden_reply();
    let mut value = request(Some(&reply), &["violations", "dependency_edges"]);
    let edges = &frame(&value)["sections"]["dependency_edges"];
    // Each edge row holds its ranks; the old field `edges` without ranks is gone.
    assert!(edges.as_array().is_some_and(|rows| {
        !rows.is_empty()
            && rows.iter().all(|row| {
                row["data"]["source_rank"].is_u64() && row["data"]["target_rank"].is_u64()
            })
    }));
    assert!(frame(&value)["edges"].is_null());
    value["profile"] = json!("other");
    let got = frame(&value);
    assert!(names_a_gap(&value));
    assert!(got["sections"]["dependency_edges"].is_null());
    assert!(got["unsupported"]["sections"]["dependency_edges"]
        .as_str()
        .is_some_and(|text| text.contains("refused settings: the profile")));
    let reasons = got["unsupported"]["rules"]
        .as_object()
        .cloned()
        .unwrap_or_default();
    assert!(reasons.values().any(|reason| reason
        .as_str()
        .is_some_and(|text| text.contains("refused settings: the profile"))));
}

#[test]
fn the_sections_of_slice_s3_need_no_contract_that_the_core_can_use() {
    let reply = golden_reply();
    let sections = [
        "dependency_edges",
        "modules",
        "packages",
        "cycles",
        "violations",
    ];
    let mut value = request(Some(&reply), &sections);
    value["contracts"] = json!({"architecture-contract.json": "{not a contract"});
    let got = frame(&value);
    for section in ["dependency_edges", "modules", "packages", "cycles"] {
        assert!(got["sections"][section].is_array(), "{section}");
    }
    assert!(got["sections"]["modules"]
        .as_array()
        .is_some_and(|rows| !rows.is_empty()));
    // The violations need the model, so they name the missing contract.
    assert_eq!(
        got["unsupported"]["sections"]["violations"],
        "missing input: no valid contract"
    );
}

fn hex_of(bytes: &[u8]) -> String {
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}

const MOUNTING: &str = r#"{"schema_version": "3.14.0", "rules": [], "components": [{"id": "C-a",
  "label": "a", "role": "component", "packages": ["p.a"], "responsibilities": ["Own a."],
  "forbidden_responsibilities": [], "provenance": ["d.md"], "inside": "a.json"}]}"#;
const LEAF: &[u8] = br#"{"schema_version": "3.14.0", "components": [], "rules": []}"#;

#[test]
fn a_tree_names_its_missing_paths_and_assembles_from_the_inside_files_of_the_request() {
    let mut first = request(None, &[]);
    first["contracts"] = json!({"architecture-contract.json": MOUNTING});
    let got = frame(&first);
    assert_eq!(got["self_test"]["contract"], json!({"missing": ["a.json"]}));
    assert!(got["unsupported"]["rules"]
        .as_str()
        .is_some_and(|text| text.ends_with("not sent: a.json")));
    assert!(names_a_gap(&first));
    let mut second = first.clone();
    second["insides"] = json!([{"reference": "a.json", "identity": "a.json", "hex": hex_of(LEAF)}]);
    let got = frame(&second);
    assert_eq!(got["self_test"]["contract"], json!({"rules": {}}));
}

#[test]
fn an_inside_file_with_bad_hex_too_many_files_or_too_many_bytes_is_refused() {
    let mut bad = request(None, &[]);
    bad["insides"] = json!([{"reference": "a.json", "identity": "a.json", "hex": "zz"}]);
    assert!(answer(bad.to_string().as_bytes()).is_err());
    let mut extra = request(None, &[]);
    extra["insides"] = json!([{"reference": "a", "identity": "a", "hex": "", "more": 1}]);
    assert!(answer(extra.to_string().as_bytes()).is_err());
    let mut many = request(None, &[]);
    let one = json!({"reference": "a.json", "identity": "a.json", "hex": ""});
    many["insides"] = Value::Array(vec![one; crate::contract::MAX_INSIDE_FILES + 1]);
    let error = answer(many.to_string().as_bytes())
        .err()
        .unwrap_or_default();
    assert!(
        error.contains("inside contracts; the core reads at most"),
        "{error}"
    );
    let mut large = request(None, &[]);
    let digits = "20".repeat(crate::contract::MAX_INSIDE_BYTES + 1);
    large["insides"] = json!([{"reference": "a.json", "identity": "a.json", "hex": digits}]);
    let error = answer(large.to_string().as_bytes())
        .err()
        .unwrap_or_default();
    assert!(error.contains("bytes; the core reads no more"), "{error}");
}
