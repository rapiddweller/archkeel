// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: package resolution. Each expected value was printed by the Python resolver
// (`_declares_exports`, `_export_condition` and the target pattern of `_export_target`).

use serde_json::json;

use super::*;

fn manifest(value: serde_json::Value) -> Json {
    value.as_object().cloned().unwrap_or_default()
}

#[test]
fn exports_count_as_declared_like_javascript_truthiness() {
    let declared = [
        (json!({}), false),
        (json!({"exports": null}), false),
        (json!({"exports": false}), false),
        (json!({"exports": ""}), false),
        (json!({"exports": 0}), false),
        (json!({"exports": 0.0}), false),
        (json!({"exports": "./x"}), true),
        (json!({"exports": {}}), true),
        (json!({"exports": []}), true),
        (json!({"exports": 1}), true),
        (json!({"exports": true}), true),
    ];
    for (value, expected) in declared {
        assert_eq!(
            declares_exports(&manifest(value.clone())),
            expected,
            "{value}"
        );
    }
}

#[test]
fn a_target_must_be_a_plain_package_path() {
    let accepted = ["./a.js", "./a/b.js"];
    let refused = [
        "./",
        "./a/",
        "./a//b",
        "./a/../b",
        "./a/./b",
        "./node_modules/x",
        "./a%20b",
        "./a?b",
        "./a#b",
        "./a\\b",
        "a.js",
        "../a",
        ".//a",
    ];
    for target in accepted {
        assert!(plain_target(target), "{target}");
    }
    for target in refused {
        assert!(!plain_target(target), "{target}");
    }
}

fn selected_target(value: serde_json::Value, esm: bool) -> String {
    match condition(&value, esm) {
        Condition::Target(target) => target,
        Condition::Unknown(unknown) => {
            format!("unknown:{}:{}", unknown.reason, unknown.package_internal)
        }
        Condition::Nothing => "nothing".to_owned(),
    }
}

#[test]
fn the_first_active_condition_decides_in_file_order() {
    let cases = [
        (
            json!({"types": "./t", "import": "./i", "require": "./r"}),
            true,
            "./t",
        ),
        (json!({"import": "./i", "require": "./r"}), false, "./r"),
        (
            json!({"node": "./n"}),
            true,
            "unknown:Package exports condition is not observed: node:true",
        ),
        (json!({"default": {"import": "./d"}}), false, "nothing"),
        (json!({"require": "./r", "default": "./d"}), true, "./d"),
        (
            json!({"default": 7}),
            true,
            "unknown:Package exports conditions are not observed:false",
        ),
        (
            json!({"types": null}),
            true,
            "unknown:Package exports conditions are not observed:false",
        ),
        (json!("./s"), true, "./s"),
    ];
    for (value, esm, expected) in cases {
        assert_eq!(
            selected_target(value.clone(), esm),
            expected,
            "{value} esm={esm}"
        );
    }
}
