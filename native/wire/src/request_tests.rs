// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the collector binary reads exactly what `facts_codec.encode_request` writes.

use serde_json::{json, Value};

use super::*;
use crate::protocol::{reply_version, Version};
use archkeel_facts::envelope::{Dirty, UnknownDirty};
use archkeel_facts::request::Request;
use archkeel_facts::request::{PythonPhase, PythonRequest};

fn request(version: &str) -> Value {
    json!({
        "protocol_version": version,
        "snapshot": {"root": "/repository", "git_head": "a".repeat(40), "dirty": false},
        "scope": {"roots": ["src"], "namespace": "shop"},
        "resolver": {"language": "typescript", "tsconfig": "tsconfig.json"},
    })
}

fn decoded(value: &Value) -> Result<TypeScriptRequest, String> {
    decode(&serde_json::to_vec(value).unwrap())
}

#[test]
fn a_request_encodes_back_to_the_value_it_was_decoded_from() {
    let mut bundler = request("8.0.0");
    bundler["resolver"]["bundler"] = json!(true);
    let mut unknown = request("3.0.0");
    unknown["snapshot"]["dirty"] = json!("unknown");
    let mut v9 = request("9.0.0");
    v9["scope"]["exclude_test_sources"] = json!(false);
    let mut rust = request("8.0.0");
    rust["resolver"] = json!({"language": "rust"});
    for value in [
        request("3.0.0"),
        request("8.0.0"),
        bundler,
        unknown,
        v9,
        rust,
    ] {
        let typed: Request = serde_json::from_value(value.clone()).unwrap();
        assert_eq!(serde_json::to_value(&typed).unwrap(), value);
    }
}

#[test]
fn a_field_that_the_request_does_not_know_or_a_wrong_type_is_refused() {
    let mut value = request("8.0.0");
    value["extra"] = json!(1);
    assert!(decoded(&value)
        .unwrap_err()
        .contains("unknown field `extra`"));
    for (pointer, replacement, text) in [
        ("/snapshot/git_head", json!(1), "invalid type: integer"),
        ("/scope/roots", json!("src"), "invalid type: string"),
        ("/resolver/tsconfig", json!(null), "invalid type: null"),
        (
            "/resolver/language",
            json!("dart"),
            "unknown variant `dart`",
        ),
    ] {
        let mut value = request("8.0.0");
        *value.pointer_mut(pointer).unwrap() = replacement;
        let error = decoded(&value).unwrap_err();
        assert!(error.starts_with("invalid collection request: "), "{error}");
        assert!(error.contains(text), "{pointer}: {error}");
    }
    let mut value = request("8.0.0");
    value["snapshot"].as_object_mut().unwrap().remove("dirty");
    assert!(decoded(&value)
        .unwrap_err()
        .contains("missing field `dirty`"));
}

#[test]
fn decodes_the_requests_the_host_sends_to_typescript() {
    for (text, version) in [("3.0.0", Version::V3), ("8.0.0", Version::V8)] {
        let request = decoded(&request(text)).unwrap();
        assert_eq!(request.protocol_version, version);
        assert_eq!(request.scope.roots, ["src"]);
        assert_eq!(request.scope.namespace, "shop");
        assert_eq!(request.resolver.tsconfig, "tsconfig.json");
        assert!(!request.resolver.bundler && !request.excludes_test_sources());
    }
}

#[test]
fn version_9_carries_the_test_scope_and_older_versions_refuse_it() {
    let mut value = request("9.0.0");
    assert_eq!(decoded(&value).unwrap_err(), "scope fields mismatch");
    value["scope"]["exclude_test_sources"] = json!(true);
    let request_v9 = decoded(&value).unwrap();
    assert!(request_v9.excludes_test_sources());
    assert_eq!(request_v9.protocol_version, Version::V9);
    value["protocol_version"] = json!("8.0.0");
    assert_eq!(decoded(&value).unwrap_err(), "scope fields mismatch");
}

#[test]
fn the_reply_version_is_the_version_the_host_accepts() {
    assert_eq!(reply_version(Version::V3), Version::V8);
    assert_eq!(reply_version(Version::V8), Version::V8);
    assert_eq!(reply_version(Version::V9), Version::V9);
    assert_eq!(reply_version(Version::V10), Version::V10);
}

#[test]
fn refuses_versions_the_typescript_host_never_sends() {
    for version in ["1.0.0", "7.0.0", "11.0.0", ""] {
        let error = decoded(&request(version)).unwrap_err();
        assert!(
            error.contains(
                "unsupported collection protocol version, expected one of 3.0.0, 8.0.0, 9.0.0, \
                 10.0.0"
            ),
            "{error}"
        );
    }
}

#[test]
fn bundler_is_present_only_when_true() {
    let mut value = request("8.0.0");
    value["resolver"]["bundler"] = json!(true);
    assert!(decoded(&value).unwrap().resolver.bundler);
    value["resolver"]["bundler"] = json!(false);
    let error = decoded(&value).unwrap_err();
    assert!(
        error.contains("resolver.bundler must be true when present"),
        "{error}"
    );
}

#[test]
fn refuses_other_languages_and_unsafe_paths() {
    let mut value = request("8.0.0");
    value["resolver"] = json!({"language": "dart"});
    assert!(decoded(&value)
        .unwrap_err()
        .contains("unknown variant `dart`"));
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
        let error = decoded(&value).unwrap_err();
        assert!(error.contains(message), "{pointer}: {error}");
    }
}

#[test]
fn accepts_windows_roots_and_the_unknown_dirty_state() {
    let mut value = request("3.0.0");
    value["snapshot"]["root"] = json!(concat!("C", ":\\work\\repository"));
    value["snapshot"]["dirty"] = json!("unknown");
    let request = decoded(&value).unwrap();
    assert_eq!(
        request.snapshot.dirty,
        Dirty::Unknown(UnknownDirty::Unknown)
    );
    value["snapshot"]["root"] = json!(concat!("C", ":\\work/repository"));
    assert!(decoded(&value).is_err());
}

#[test]
fn a_rust_request_has_a_resolver_with_one_field() {
    let mut value = request("8.0.0");
    value["resolver"] = json!({"language": "rust"});
    let rust = decode_rust(&serde_json::to_vec(&value).unwrap()).unwrap();
    assert_eq!(rust.resolver, archkeel_facts::request::RustSettings {});
    value["resolver"] = json!({"language": "rust", "tsconfig": "tsconfig.json"});
    let refused = decode_rust(&serde_json::to_vec(&value).unwrap());
    assert!(refused.unwrap_err().contains("unknown field `tsconfig`"));
    value["resolver"] = json!({"language": "typescript", "tsconfig": "tsconfig.json"});
    let refused = decode_rust(&serde_json::to_vec(&value).unwrap());
    assert_eq!(
        refused.unwrap_err(),
        "Rust collector requires the Rust resolver"
    );
    value["resolver"] = json!({"language": "rust"});
    assert_eq!(
        decoded(&value).unwrap_err(),
        "TypeScript collector requires the TypeScript resolver"
    );
}

fn python(version: &str) -> Value {
    let mut value = request(version);
    value["scope"]["exclude_test_sources"] = json!(false);
    value["resolver"] = json!({
        "language": "python",
        "phase": "imports",
        "interpreter": {
            "version": "3.11.12",
            "stdlib_module_names": ["abc", "os"],
            "builtin_module_names": ["sys"],
        },
    });
    value
}

fn decoded_python(value: &Value) -> Result<PythonRequest, String> {
    decode_python(&serde_json::to_vec(value).unwrap())
}

#[test]
fn a_python_request_is_version_10_and_carries_the_interpreter_block() {
    let value = python("10.0.0");
    let typed = decoded_python(&value).unwrap();
    assert_eq!(typed.protocol_version, Version::V10);
    assert_eq!(typed.resolver.phase, PythonPhase::Imports);
    assert_eq!(typed.resolver.interpreter.version, "3.11.12");
    let whole: Request = serde_json::from_value(value.clone()).unwrap();
    assert_eq!(serde_json::to_value(&whole).unwrap(), value);
    assert_eq!(
        decoded(&value).unwrap_err(),
        "TypeScript collector requires the TypeScript resolver"
    );
}

#[test]
fn the_python_resolver_and_version_10_need_each_other() {
    let mut old = python("9.0.0");
    assert_eq!(
        decoded_python(&old).unwrap_err(),
        "the Python resolver requires protocol 10.0.0"
    );
    old["protocol_version"] = json!("8.0.0");
    old["scope"]
        .as_object_mut()
        .unwrap()
        .remove("exclude_test_sources");
    assert!(decoded_python(&old).is_err());
    let mut typescript = request("10.0.0");
    typescript["scope"]["exclude_test_sources"] = json!(false);
    assert_eq!(
        decoded(&typescript).unwrap_err(),
        "protocol 10.0.0 requires the Python resolver"
    );
}

#[test]
fn the_interpreter_block_is_closed_and_checked() {
    let cases = [
        (
            "/resolver/interpreter/extra",
            json!(1),
            "unknown field `extra`",
        ),
        (
            "/resolver/phase",
            json!("providers"),
            "unknown variant `providers`",
        ),
        (
            "/resolver/interpreter/version",
            json!("3.10.4"),
            "Python 3.11 to 3.14",
        ),
        (
            "/resolver/interpreter/version",
            json!("3.15.0"),
            "Python 3.11 to 3.14",
        ),
        (
            "/resolver/interpreter/version",
            json!("3.11"),
            "a full Python version",
        ),
        (
            "/resolver/interpreter/version",
            json!("2.7.18"),
            "a full Python version",
        ),
        (
            "/resolver/interpreter/stdlib_module_names",
            json!(["os", "abc"]),
            "stdlib_module_names must be sorted and unique",
        ),
        (
            "/resolver/interpreter/builtin_module_names",
            json!(["sys", "sys"]),
            "builtin_module_names must be sorted and unique",
        ),
        (
            "/resolver/interpreter/builtin_module_names",
            json!(["no-name"]),
            "builtin_module_names must hold module names",
        ),
    ];
    for (pointer, replacement, message) in cases {
        let mut value = python("10.0.0");
        let (parent, key) = pointer.rsplit_once('/').unwrap();
        value.pointer_mut(parent).unwrap()[key] = replacement;
        let error = decoded_python(&value).unwrap_err();
        assert!(error.contains(message), "{pointer}: {error}");
    }
    let hostile = [
        "3.11.1\u{0}",
        "3.11.1 junk",
        "+3.11.1",
        "03.11.1",
        "3.11.1.4",
        "3.011.1",
        "3.11.01",
        "3.11.1rc",
        "3.11.1x1",
        "3.11.1++",
        "3.11.",
        "3.11.1+rc1",
    ];
    for version in hostile {
        let mut value = python("10.0.0");
        value["resolver"]["interpreter"]["version"] = json!(version);
        let error = decoded_python(&value).unwrap_err();
        assert!(
            error.contains("a full Python version"),
            "{version:?}: {error}"
        );
    }
    for version in [
        "3.14.0rc1",
        "3.13.0a2",
        "3.12.0b4",
        "3.12.10+",
        "3.13.0rc2+",
        "3.11.0",
    ] {
        let mut value = python("10.0.0");
        value["resolver"]["interpreter"]["version"] = json!(version);
        assert!(decoded_python(&value).is_ok(), "{version}");
    }
}

#[test]
fn a_duplicate_key_is_refused_because_the_request_is_ambiguous() {
    let text = r#"{"protocol_version":"8.0.0","snapshot":{"root":"/r","git_head":"a","dirty":false},
        "scope":{"roots":["src"],"namespace":"shop","namespace":"other"},
        "resolver":{"language":"typescript","tsconfig":"tsconfig.json"}}"#;
    let error = decode(text.as_bytes()).unwrap_err();
    assert!(error.contains("duplicate field `namespace`"), "{error}");
}
