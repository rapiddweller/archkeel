// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

use std::io::{Read, Write};

use flate2::read::ZlibDecoder;
use flate2::write::ZlibEncoder;
use flate2::Compression;
use serde_json::{json, Value};

use archkeel_model::Producer;

use super::{answer, stage_one_shell_trust, CODE_DIGEST, PRODUCER_NOT_VERIFIED};
use crate::engine::tests::{golden_reply, NATIVE_CONTRACT};

fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|byte| format!("{byte:02x}")).collect()
}

/// The frozen reply with another adapter name or code digest.
fn reply_with(name: Option<&str>, digest: &str) -> Vec<u8> {
    let mut text = String::new();
    let _ = ZlibDecoder::new(golden_reply().as_slice()).read_to_string(&mut text);
    let mut value: Value = serde_json::from_str(&text).unwrap_or(Value::Null);
    if let Some(name) = name {
        value["facts"]["adapter"]["name"] = json!(name);
    }
    value["facts"]["adapter"]["code_digest"] = json!(digest);
    let mut encoder = ZlibEncoder::new(Vec::new(), Compression::fast());
    let _ = encoder.write_all(value.to_string().as_bytes());
    encoder.finish().unwrap_or_default()
}

fn request(reply: Option<&[u8]>) -> Value {
    json!({
        "protocol": "archkeel-core-check-2",
        "contract": {"path": "architecture-contract.json", "hex": hex(NATIVE_CONTRACT.as_bytes())},
        "insides": [],
        "reply": reply.map(|bytes| json!({"hex": hex(bytes)})),
        "roots": [],
        "namespace": "shop",
        "base": null,
    })
}

/// The one gap of a request without provenance documents (AD-466).
const HYGIENE: fn() -> Value = || {
    json!({"hygiene:request":
        "unsupported: the contract hygiene of the request: it carries no provenance documents"})
};

fn frame(value: &Value) -> (Value, bool) {
    match answer(value.to_string().as_bytes()) {
        Ok(answered) => (
            serde_json::from_slice(&answered.frame).unwrap_or(Value::Null),
            answered.names_a_gap,
        ),
        Err(message) => (json!({ "error": message }), true),
    }
}

#[test]
fn a_reply_of_the_collector_of_this_build_is_decided_without_a_gap() {
    let (got, names_a_gap) = frame(&request(Some(&reply_with(None, CODE_DIGEST))));
    // AD-466: the check request reads no provenance document, so it names only that gap.
    let hygiene = HYGIENE;
    assert_eq!(got["unsupported"]["rules"], hygiene(), "{got}");
    assert!(names_a_gap);
    // The frame names no report part: the check request asks for no report payload.
    assert_eq!(got["unsupported"]["report"], Value::Null);
    assert_eq!(got["rules"].as_object().map_or(0, |rules| rules.len()), 83);
    // The contract does not fit this reply: each rule is a decided UNKNOWN with its reason.
    assert_eq!(got["status"], "UNKNOWN");
}

#[test]
fn a_reply_with_another_code_digest_names_the_whole_contract() {
    let (got, names_a_gap) = frame(&request(Some(&golden_reply())));
    let reason = got["unsupported"]["rules"].as_str().unwrap_or_default();
    assert!(reason.starts_with(PRODUCER_NOT_VERIFIED), "{got}");
    assert!(names_a_gap);
    assert_eq!(got["rules"], json!({}));
    assert_eq!(got["status"], "UNKNOWN");
}

#[test]
fn a_reply_of_another_adapter_with_the_digest_of_this_build_is_not_verified() {
    let (got, names_a_gap) = frame(&request(Some(&reply_with(Some("other"), CODE_DIGEST))));
    let reason = got["unsupported"]["rules"].as_str().unwrap_or_default();
    assert!(reason.starts_with(PRODUCER_NOT_VERIFIED), "{got}");
    assert!(names_a_gap);
}

#[test]
fn a_request_that_states_trust_is_refused() {
    let reply = reply_with(None, CODE_DIGEST);
    for (field, value) in [
        ("pinned", json!(true)),
        ("producer", json!("trusted")),
        ("profile", json!("archkeel-rust-imports")),
        ("standard_library", json!(["transport"])),
        ("collector_argv", Value::Null),
        ("settings", json!({})),
    ] {
        let mut hostile = request(Some(&reply));
        hostile[field] = value;
        let (got, _) = frame(&hostile);
        let error = got["error"].as_str().unwrap_or_default();
        assert!(error.contains("unknown field"), "{field}: {got}");
    }
}

#[test]
fn a_request_of_another_protocol_or_without_a_field_is_refused() {
    let mut other = request(None);
    other["protocol"] = json!("archkeel-dual-run-4");
    assert!(frame(&other).0["error"].is_string());
    let mut missing = request(None);
    if let Some(object) = missing.as_object_mut() {
        object.remove("roots");
    }
    assert!(frame(&missing).0["error"].is_string());
}

#[test]
fn a_request_without_a_reply_names_a_gap() {
    let (got, names_a_gap) = frame(&request(None));
    assert!(got["self_test"]["reply"]["absent"].is_string(), "{got}");
    assert!(names_a_gap);
    assert_eq!(got["status"], "UNKNOWN");
}

/// AD-390 point 2: the check request reaches `Producer::Trusted` only through
/// `stage_one_shell_trust`, and only for the collector of the profile with the digest of this
/// build. Each other reply names the whole contract.
#[test]
fn stage_one_shell_trust_trusts_only_the_collector_of_this_build() {
    let trusted = |name: Option<&str>, digest: &str| {
        let bytes = reply_with(name, digest);
        let reply = archkeel_store::ingest_reply(&bytes, 1 << 30).ok();
        let trust = stage_one_shell_trust("shop".to_owned(), reply.as_ref());
        (trust.settings.producer(), trust.gap)
    };
    let (producer, gap) = trusted(None, CODE_DIGEST);
    assert_eq!((producer, gap), (Producer::Trusted, None));
    let other = "1".repeat(64);
    let zero = "0".repeat(64);
    for (name, digest) in [
        (None, other.as_str()),
        (None, zero.as_str()),
        (Some("x"), CODE_DIGEST),
    ] {
        let (producer, gap) = trusted(name, digest);
        assert_eq!(producer, Producer::External, "{name:?} {digest}");
        assert!(gap.is_some_and(|why| why.starts_with(PRODUCER_NOT_VERIFIED)));
    }
    // A missing digest is not a digest: the store refuses the reply, so there is no trust.
    let (producer, gap) = trusted(None, "");
    assert_eq!((producer, gap), (Producer::External, None));
}
