// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the vendored libraries. The expected problems are those of `config._script_environment`
// (`options_tests.rs` has the same case through a whole config).

use serde_json::json;

use super::*;

fn read_json(value: &serde_json::Value) -> (ScriptEnvironment, Vec<String>) {
    let mut problems = Vec::new();
    let raw = value.as_object();
    (read(raw, &mut problems), problems)
}

#[test]
fn a_config_without_the_object_declares_nothing() {
    let (environment, problems) = read_json(&json!({"compilerOptions": {}}));
    assert!(!environment.classic_browser && environment.providers.is_empty());
    assert!(problems.is_empty());
    assert!(read(None, &mut Vec::new()).providers.is_empty());
}

#[test]
fn a_classic_browser_and_its_providers_are_read_in_order() {
    let (environment, problems) = read_json(&json!({"archkeel": {
        "scriptHost": "classic-browser",
        "scriptProviders": [
            {"source": "v/a.js", "provenance": "v/A.md"},
            {"source": "v/b.js", "provenance": "v/B.md"}
        ]
    }}));
    assert!(problems.is_empty());
    assert!(environment.classic_browser);
    let sources: Vec<&str> = environment
        .providers
        .iter()
        .map(|p| p.source.as_str())
        .collect();
    assert_eq!(sources, ["v/a.js", "v/b.js"]);
}

#[test]
fn every_wrong_part_is_one_problem() {
    let (_, problems) = read_json(&json!({"archkeel": {"other": 1}}));
    assert_eq!(
        problems,
        ["Archkeel script environment is not a closed object"]
    );
    let (environment, problems) = read_json(&json!({"archkeel": {"scriptHost": "node"}}));
    assert_eq!(problems, ["Archkeel script host is not supported"]);
    assert!(!environment.classic_browser);
    let (_, problems) = read_json(&json!({"archkeel": {"scriptProviders": "x"}}));
    assert_eq!(problems, ["Archkeel script providers must be a list"]);
    let provider = json!({"source": "a.js", "provenance": "a.md"});
    let (environment, problems) = read_json(&json!({"archkeel": {"scriptProviders": [
        provider, provider, {"source": "/abs", "provenance": "b"}, {"source": "../x", "provenance": "b"},
        {"source": "a", "provenance": "b", "extra": 1}, 5
    ]}}));
    assert_eq!(environment.providers.len(), 2);
    assert_eq!(
        problems
            .iter()
            .filter(|p| p.contains("two snapshot-relative"))
            .count(),
        4
    );
    assert_eq!(
        problems
            .iter()
            .filter(|p| p.contains("more than once"))
            .count(),
        1
    );
}
