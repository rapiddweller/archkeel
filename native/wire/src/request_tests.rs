// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the collector binary reads exactly what `facts_codec.encode_request` writes.

use serde_json::{json, Value};

use super::*;
use crate::protocol::{reply_version, Version};

fn request(version: &str) -> Value {
    json!({
        "protocol_version": version,
        "snapshot": {"root": "/repository", "git_head": "a".repeat(40), "dirty": false},
        "scope": {"roots": ["src"], "namespace": "shop"},
        "resolver": {"language": "typescript", "tsconfig": "tsconfig.json"},
    })
}

fn decoded(value: &Value) -> Result<Request, String> {
    decode(&serde_json::to_vec(value).unwrap())
}

#[test]
fn decodes_the_requests_the_host_sends_to_typescript() {
    for (text, version) in [("3.0.0", Version::V3), ("8.0.0", Version::V8)] {
        let request = decoded(&request(text)).unwrap();
        assert_eq!(request.version, version);
        assert_eq!(request.roots, ["src"]);
        assert_eq!(request.namespace, "shop");
        assert_eq!(request.tsconfig, "tsconfig.json");
        assert!(!request.bundler && !request.exclude_test_sources);
    }
}

#[test]
fn version_9_carries_the_test_scope_and_older_versions_refuse_it() {
    let mut value = request("9.0.0");
    assert_eq!(decoded(&value).unwrap_err(), "scope fields mismatch");
    value["scope"]["exclude_test_sources"] = json!(true);
    let request_v9 = decoded(&value).unwrap();
    assert!(request_v9.exclude_test_sources);
    assert_eq!(request_v9.version, Version::V9);
    value["protocol_version"] = json!("8.0.0");
    assert_eq!(decoded(&value).unwrap_err(), "scope fields mismatch");
}

#[test]
fn the_reply_version_is_the_version_the_host_accepts() {
    assert_eq!(reply_version(Version::V3), Version::V8);
    assert_eq!(reply_version(Version::V8), Version::V8);
    assert_eq!(reply_version(Version::V9), Version::V9);
}

#[test]
fn refuses_versions_the_typescript_host_never_sends() {
    for version in ["1.0.0", "7.0.0", "10.0.0", ""] {
        assert_eq!(
            decoded(&request(version)).unwrap_err(),
            "unsupported collection protocol version"
        );
    }
}

#[test]
fn bundler_is_present_only_when_true() {
    let mut value = request("8.0.0");
    value["resolver"]["bundler"] = json!(true);
    assert!(decoded(&value).unwrap().bundler);
    value["resolver"]["bundler"] = json!(false);
    assert_eq!(
        decoded(&value).unwrap_err(),
        "resolver.bundler must be true when present"
    );
}

#[test]
fn refuses_other_languages_and_unsafe_paths() {
    let mut value = request("8.0.0");
    value["resolver"] = json!({"language": "python"});
    assert_eq!(
        decoded(&value).unwrap_err(),
        "TypeScript collector requires the TypeScript resolver"
    );
    let cases = [
        (
            "/snapshot/root",
            json!("relative/root"),
            "snapshot.root must be an absolute path",
        ),
        (
            "/scope/roots",
            json!(["../src"]),
            "scope.roots must stay inside the snapshot",
        ),
        (
            "/scope/roots",
            json!(["src", "src/a"]),
            "scope.roots must not overlap",
        ),
        (
            "/scope/roots",
            json!(["src", "src"]),
            "scope.roots must not repeat",
        ),
        (
            "/scope/roots",
            json!([]),
            "scope.roots must be a nonempty array",
        ),
        (
            "/scope/namespace",
            json!("shop-x"),
            "scope.namespace must be a dotted namespace",
        ),
        (
            "/snapshot/dirty",
            json!("yes"),
            "snapshot.dirty must be a boolean or unknown",
        ),
    ];
    for (pointer, replacement, message) in cases {
        let mut value = request("8.0.0");
        *value.pointer_mut(pointer).unwrap() = replacement;
        assert_eq!(decoded(&value).unwrap_err(), message, "{pointer}");
    }
}

#[test]
fn accepts_windows_roots_and_the_unknown_dirty_state() {
    let mut value = request("3.0.0");
    value["snapshot"]["root"] = json!(concat!("C", ":\\work\\repository"));
    value["snapshot"]["dirty"] = json!("unknown");
    let request = decoded(&value).unwrap();
    assert_eq!(request.dirty, json!("unknown"));
    value["snapshot"]["root"] = json!(concat!("C", ":\\work/repository"));
    assert!(decoded(&value).is_err());
}
