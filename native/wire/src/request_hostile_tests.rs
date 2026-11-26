// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Hostile bytes at the collector request decoder (#1001): each one gives a typed refusal in
// bounded time and never a panic. The four decoders share one parser, so each case runs on all.

use std::time::{Duration, Instant};

use serde_json::{json, Value};

use super::*;

type Decoder = fn(&[u8]) -> Result<(), String>;

fn decoders() -> [(&'static str, Decoder); 4] {
    [
        ("typescript", |bytes| decode(bytes).map(drop)),
        ("rust", |bytes| decode_rust(bytes).map(drop)),
        ("python", |bytes| decode_python(bytes).map(drop)),
        ("dart", |bytes| decode_dart(bytes).map(drop)),
    ]
}

fn refused_by_all(input: &[u8]) {
    for (name, decoder) in decoders() {
        let started = Instant::now();
        let result = decoder(input);
        assert!(
            started.elapsed() < Duration::from_secs(10),
            "{name}: a hang"
        );
        let error = result.expect_err(name);
        assert!(!error.is_empty(), "{name}: an empty refusal");
    }
}

fn valid() -> Value {
    json!({
        "protocol_version": "8.0.0",
        "snapshot": {"root": "/repository", "git_head": "a".repeat(40), "dirty": false},
        "scope": {"roots": ["src"], "namespace": "shop"},
        "resolver": {"language": "typescript", "tsconfig": "tsconfig.json"},
    })
}

#[test]
fn malformed_and_truncated_payloads_are_refused() {
    refused_by_all(b"");
    refused_by_all(b"null");
    refused_by_all(b"[]");
    refused_by_all(b"{}");
    refused_by_all(b"\xff\xfe");
    refused_by_all(b"{\"protocol_version\":\"8.0.0\"} trailing");
    let whole = valid().to_string();
    for cut in 0..whole.len() {
        let prefix = &whole.as_bytes()[..cut];
        if std::str::from_utf8(prefix).is_ok() {
            for (name, decoder) in decoders() {
                assert!(decoder(prefix).is_err(), "{name}: prefix of {cut} bytes");
            }
        }
    }
}

#[test]
fn deep_nesting_is_refused_without_a_stack_overflow() {
    for depth in [200, 100_000, 2_000_000] {
        refused_by_all(format!("{}1{}", "[".repeat(depth), "]".repeat(depth)).as_bytes());
        refused_by_all(format!("{}1{}", "{\"a\":".repeat(depth), "}".repeat(depth)).as_bytes());
        let mut value = valid();
        let nested = format!("{}1{}", "[".repeat(depth), "]".repeat(depth));
        value["scope"]["roots"] = serde_json::from_str(&nested).unwrap_or(json!(0));
        refused_by_all(value.to_string().as_bytes());
    }
}

#[test]
fn a_long_string_or_a_long_list_gives_a_refusal_or_a_bounded_decode() {
    for field in ["/snapshot/root", "/snapshot/git_head", "/scope/namespace"] {
        let mut value = valid();
        *value.pointer_mut(field).unwrap() = json!(format!("/{}", "a".repeat(8 << 20)));
        let started = Instant::now();
        let result = decode(value.to_string().as_bytes());
        assert!(
            started.elapsed() < Duration::from_secs(10),
            "{field}: a hang"
        );
        // The worker reads at most 1 MiB of request, so a long string never gets this far
        // there (`serve_v1`); the decoder itself only needs to answer in bounded time.
        let _ = result;
    }
    let mut value = valid();
    value["scope"]["roots"] = json!((0..200_000).map(|n| format!("src{n}")).collect::<Vec<_>>());
    let started = Instant::now();
    let _ = decode(value.to_string().as_bytes());
    assert!(
        started.elapsed() < Duration::from_secs(10),
        "many roots: a hang"
    );
}

#[test]
fn a_path_that_leaves_the_repository_is_refused_in_every_spelling() {
    for path in [
        "..",
        "../x",
        "src/../../x",
        "/etc/passwd",
        "\\\\server\\share",
        "C:\\x",
        "C:/x",
        "src\u{0}x",
        "",
    ] {
        let mut value = valid();
        value["scope"]["roots"] = json!([path]);
        assert!(
            decode(value.to_string().as_bytes()).is_err(),
            "root {path:?}"
        );
        let mut value = valid();
        value["resolver"]["tsconfig"] = json!(path);
        assert!(
            decode(value.to_string().as_bytes()).is_err(),
            "tsconfig {path:?}"
        );
    }
}

#[test]
fn a_name_that_could_reach_a_shell_or_a_file_name_is_refused_as_a_namespace() {
    for name in [
        "a;rm -rf x",
        "a b",
        "$(x)",
        "a/../b",
        "a\nb",
        "<script>",
        "a..b",
        ".",
    ] {
        let mut value = valid();
        value["scope"]["namespace"] = json!(name);
        assert!(decode(value.to_string().as_bytes()).is_err(), "{name:?}");
    }
}

#[test]
fn roots_that_repeat_or_overlap_are_refused_wherever_they_stand_in_the_list() {
    let refused = |roots: Value| {
        let mut value = valid();
        value["scope"]["roots"] = roots;
        decode(value.to_string().as_bytes()).unwrap_err()
    };
    assert!(refused(json!(["src", "lib", "src"])).contains("repeat"));
    assert!(refused(json!(["src/a", "lib", "src"])).contains("overlap"));
    assert!(refused(json!(["a", "a/b/c", "a/b", "z"])).contains("overlap"));
    assert!(refused(json!(["src", "./src/x", "b"])).contains("overlap"));
    let mut value = valid();
    value["scope"]["roots"] = json!(["src", "src2", "src-a", "lib/a", "lib/b"]);
    assert!(decode(value.to_string().as_bytes()).is_ok());
}
