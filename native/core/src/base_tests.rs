// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! AD-399: the base reply of a check request. The core reads it through the trust function of the
//! request kind and derives its model itself; a base that it cannot read names the whole contract.

use serde_json::{json, Value};

use super::BASE;
use crate::check::{answer, CODE_DIGEST, PRODUCER_NOT_VERIFIED};
use crate::engine::tests::golden_reply_with;

/// A contract without rules: the run of the frozen reply passes with a complete scope.
const NO_RULES: &str = r#"{"schema_version": "2.2.0", "components": [], "rules": []}"#;

fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|byte| format!("{byte:02x}")).collect()
}

/// The frozen reply of the collector of this build, after `change`.
fn reply(change: impl FnOnce(&mut Value)) -> Vec<u8> {
    golden_reply_with(|value| {
        value["facts"]["adapter"]["code_digest"] = json!(CODE_DIGEST);
        change(value);
    })
}

fn request(base: Option<&[u8]>) -> Value {
    json!({
        "protocol": "archkeel-core-check-2",
        "contract": {"path": "architecture-contract.json", "hex": hex(NO_RULES.as_bytes())},
        "insides": [],
        "reply": {"hex": hex(&reply(|_| {}))},
        "roots": [],
        "namespace": "shop",
        "base": base.map(|bytes| json!({"reply": {"hex": hex(bytes)}})),
    })
}

/// The frame, whether it names a gap, and the reason that names the whole contract.
fn frame(value: &Value) -> (Value, bool, String) {
    match answer(value.to_string().as_bytes()) {
        Ok(answered) => {
            let frame: Value = serde_json::from_slice(&answered.frame).unwrap_or(Value::Null);
            let whole = frame["unsupported"]["rules"].as_str().unwrap_or_default();
            let whole = whole.to_owned();
            (frame, answered.names_a_gap, whole)
        }
        Err(message) => (json!({ "error": message }), true, String::new()),
    }
}

/// A base gap names the whole contract, so the run is never PASS and the frame names a part.
fn assert_base_gap(value: &Value, words: &str) {
    let (got, names_a_gap, whole) = frame(value);
    assert!(whole.starts_with(&format!("{BASE}: {words}")), "{got}");
    assert!(names_a_gap);
    assert_ne!(got["status"], "PASS");
}

#[test]
fn a_base_of_this_build_keeps_the_frame_of_the_candidate() {
    let (alone, gap, _) = frame(&request(None));
    assert_eq!(
        (alone["status"].clone(), gap),
        (json!("PASS"), false),
        "{alone}"
    );
    let (with_base, gap, _) = frame(&request(Some(&reply(|_| {}))));
    assert_eq!(with_base, alone);
    assert!(!gap);
}

#[test]
fn a_base_with_another_code_digest_names_the_whole_contract() {
    let stale = reply(|value| value["facts"]["adapter"]["code_digest"] = json!("1".repeat(64)));
    assert_base_gap(&request(Some(&stale)), PRODUCER_NOT_VERIFIED);
}

#[test]
fn a_base_of_another_adapter_names_the_whole_contract() {
    let other = reply(|value| value["facts"]["adapter"]["name"] = json!("other"));
    assert_base_gap(&request(Some(&other)), PRODUCER_NOT_VERIFIED);
}

#[test]
fn a_base_that_the_store_refuses_names_the_whole_contract() {
    assert_base_gap(&request(Some(b"not a reply")), "the store refuses it");
}

/// The store refuses a reply that only changes its profile, so the compare is tested alone.
#[test]
fn a_base_of_another_profile_is_a_gap() {
    let (one, other) = (Some("profile-a"), Some("profile-b"));
    let gap = super::same_profile(one, other).err().unwrap_or_default();
    assert_eq!(
        gap,
        "its profile profile-a is not the profile profile-b of the candidate"
    );
    assert_eq!(super::same_profile(one, one), Ok(()));
    assert_eq!(super::same_profile(one, None), Ok(()));
}

#[test]
fn a_base_without_a_model_names_the_whole_contract() {
    // The scan roots bind to the base: a root that the base does not hold gives it no model.
    let mut value = request(Some(&reply(|_| {})));
    value["roots"] = json!(["a-root-that-no-file-has"]);
    assert_base_gap(&value, "it gives no model: ");
}

#[test]
fn a_request_with_a_baseline_flag_or_a_base_without_a_reply_is_refused() {
    let mut flag = request(None);
    flag["baseline"] = json!(false);
    let mut empty = request(None);
    empty["base"] = json!({});
    let mut verdict = request(Some(&reply(|_| {})));
    verdict["base"]["status"] = json!("PASS");
    let mut odd = request(None);
    odd["base"] = json!({"reply": {"hex": "abc"}});
    for hostile in [flag, empty, verdict, odd] {
        let (got, _, _) = frame(&hostile);
        assert!(got["error"].is_string(), "{hostile}: {got}");
    }
}
