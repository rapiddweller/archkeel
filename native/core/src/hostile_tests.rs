// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! A hostile request cannot decide a status, a trusted producer or the standard library
//! (#1073 items 4 and 5, AD-388). Each request is refused, or its word is ignored and the frame
//! names the gap.

use serde_json::{json, Value};

use super::answer;
use crate::engine::tests::{golden_profile, golden_reply_by, golden_reply_with};

const NO_RULES: &str = r#"{"schema_version": "2.2.0", "components": [], "rules": []}"#;
/// The contract of the H-typescript fixture: its decided rules pass on the frozen reply.
const FIXTURE: &str = include_str!("../../../fixtures/H-typescript/architecture-contract.json");
const EXTERNAL: &str = "incomplete scope: the reply does not come from the bundled collector, \
                        and the collector pin is not verified by the core";

/// A request of a contract without rules: its run passes only with a complete scope.
fn request(reply: &[u8]) -> Value {
    json!({
        "protocol": "archkeel-dual-run-5", "case": "c", "root": "/r", "config": "archkeel.toml",
        "baseline": null, "collector_argv": null,
        "contracts": {"architecture-contract.json": NO_RULES},
        "reply": {"hex": reply.iter().map(|b| format!("{b:02x}")).collect::<String>()},
        "sections": [], "namespace": "shop", "profile": golden_profile(),
        "standard_library": [], "insides": [], "roots": [],
    })
}

fn frame(value: &Value) -> Value {
    let bytes = answer(value.to_string().as_bytes()).map_or(Vec::new(), |answered| answered.frame);
    serde_json::from_slice(&bytes).unwrap_or(Value::Null)
}

/// Item 4: the request has no field for a status or a verdict; the status comes from the report.
#[test]
fn a_request_cannot_set_a_status_or_a_verdict() {
    let reply = golden_reply_by(None);
    assert_eq!(frame(&request(&reply))["status"], "PASS");
    for (field, word) in [
        ("status", json!("PASS")),
        ("rules", json!({"R": ["complete_assignment", "PASS"]})),
        ("scope", json!("complete")),
    ] {
        let mut hostile = request(&reply);
        hostile[field] = word;
        let refused = answer(hostile.to_string().as_bytes()).err();
        assert!(
            refused.is_some_and(|error| error.contains("unknown field")),
            "{field}"
        );
    }
}

/// Item 5: the claim of the bundled collector does not make the reply of another adapter trusted;
/// the frame names the producer as the scope gap.
#[test]
fn a_request_cannot_make_the_reply_of_another_adapter_trusted() {
    let foreign = golden_reply_by(Some("a-foreign-collector"));
    let bundled = frame(&request(&foreign));
    assert_eq!(
        (bundled["status"].clone(), bundled["scope"].clone()),
        (json!("UNKNOWN"), json!(EXTERNAL))
    );
}

fn passes(frame: &Value) -> usize {
    frame["rules"].as_object().map_or(0, |rules| {
        rules.values().filter(|row| row[1] == "PASS").count()
    })
}

/// L-35c, review S2 of #1090: an external collector is never trusted, because the core cannot
/// verify its pin. Before, `pinned: true` turned 0 of 8 PASS rules into 7 of 7. Now each decided
/// rule that needs the facts is UNKNOWN with the reason that names the pin, and the run is not
/// PASS.
#[test]
fn an_external_collector_is_never_trusted_and_each_rule_names_the_pin() {
    let reply = golden_reply_by(None);
    let mut bundled = request(&reply);
    bundled["contracts"] = json!({"architecture-contract.json": FIXTURE});
    assert!(passes(&frame(&bundled)) >= 6, "{}", frame(&bundled));
    let mut external = bundled.clone();
    external["collector_argv"] = json!(["/x"]);
    let got = frame(&external);
    assert_eq!(passes(&got), 0, "{got}");
    assert_eq!(got["status"], "UNKNOWN");
    assert_eq!(got["scope"], EXTERNAL);
    let explained = got["explained"].as_object().cloned().unwrap_or_default();
    assert!(explained.len() >= 6, "{got}");
    assert!(explained.values().all(|why| why == EXTERNAL), "{got}");
}

/// L-35c: a request that holds a trust statement is refused, in each spelling and nesting.
#[test]
fn a_request_with_a_pin_in_any_spelling_or_nesting_is_refused() {
    let reply = golden_reply_by(None);
    let mut hostile = Vec::new();
    for (key, value) in [
        ("pinned", json!(true)),
        ("pinned", json!(false)),
        ("pinned", json!("true")),
        ("Pinned", json!(true)),
        ("PINNED", json!(true)),
        ("pin", json!(true)),
        ("producer", json!("trusted")),
        ("pinned_digest", json!("0".repeat(64))),
    ] {
        let mut request = request(&reply);
        request["collector_argv"] = json!(["/x"]);
        request[key] = value;
        hostile.push(request);
    }
    let mut nested = request(&reply);
    nested["reply"]["pinned"] = json!(true);
    hostile.push(nested);
    let mut inside = request(&reply);
    inside["insides"] =
        json!([{"reference": "a.json", "identity": "a.json", "hex": "", "pinned": true}]);
    hostile.push(inside);
    for request in hostile {
        let refused = answer(request.to_string().as_bytes()).err();
        assert!(
            refused
                .as_ref()
                .is_some_and(|error| error.contains("unknown field")),
            "{request}: {refused:?}"
        );
    }
}

/// L-35c: reply bytes that claim a pin or the digest of this core give no trust either. A reply
/// with a field that the store does not know is refused; a reply that names the bundled adapter
/// with this core's digest is still the reply of an external collector.
#[test]
fn a_planted_reply_that_claims_a_pin_is_not_trusted() {
    let planted = golden_reply_with(|value| {
        value["facts"]["pinned"] = json!(true);
    });
    let mut refused = request(&planted);
    refused["collector_argv"] = json!(["/x"]);
    refused["contracts"] = json!({"architecture-contract.json": FIXTURE});
    let got = frame(&refused);
    assert_eq!((passes(&got), got["status"].clone()), (0, json!("UNKNOWN")));
    assert!(got["self_test"]["reply"].get("refused").is_some(), "{got}");
    let digest = env!("ARCHKEEL_CODE_DIGEST");
    let claimed = golden_reply_with(|value| {
        value["facts"]["adapter"]["code_digest"] = json!(digest);
        value["facts"]["adapter"]["version"] = json!("pinned");
    });
    let mut external = request(&claimed);
    external["collector_argv"] = json!(["/x"]);
    external["contracts"] = json!({"architecture-contract.json": FIXTURE});
    let got = frame(&external);
    assert_eq!(
        (passes(&got), got["scope"].clone()),
        (0, json!(EXTERNAL)),
        "{got}"
    );
}

/// Item 5: a standard library name outside the pinned list of the profile refuses the settings
/// by name; no rule passes on it.
#[test]
fn a_request_cannot_widen_the_standard_library() {
    let reply = golden_reply_by(None);
    let mut hostile = request(&reply);
    hostile["standard_library"] = json!(["transport"]);
    let got = frame(&hostile);
    assert_eq!(got["status"], "UNKNOWN");
    let scope = got["scope"].as_str().unwrap_or_default();
    assert!(scope.starts_with("refused settings: "), "{scope}");
    assert!(scope.contains("pinned standard library"), "{scope}");
}

/// Review M5 of #1090: the one home of the reason of a refused contract is `dual_run::named`.
/// Without it the engine names a missing contract; the status stays UNKNOWN, but the text would
/// not be true.
#[test]
fn a_refused_contract_names_its_refusal() {
    let reply = golden_reply_by(None);
    let mut refused = request(&reply);
    refused["contracts"] = json!({"architecture-contract.json": "{not json"});
    let got = frame(&refused);
    assert_eq!(got["status"], "UNKNOWN");
    let reason = got["unsupported"]["rules"].as_str().unwrap_or_default();
    assert!(reason.starts_with("refused: "), "{got}");
}
