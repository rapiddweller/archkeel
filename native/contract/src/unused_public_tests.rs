// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

use super::PublicItemKind;
use crate::contract::parse_file;
use crate::document::Contract;
use crate::rule::Rule;

fn contract(version: &str, extra: &str) -> String {
    format!(
        r#"{{"schema_version": "{version}", "components": [], "rules": [{{"id": "U",
        "kind": "unused_public", "source": "p", "rationale": "Each public name has a user.",
        "provenance": ["d.md"], "decided_by": "architect"{extra}}}]}}"#
    )
}

const USER: &str = r#"{"symbol": "p.a:f", "consumer": "a plugin", "rationale": "Not scanned."}"#;

fn read(text: &str) -> Result<Contract, String> {
    parse_file(text.as_bytes()).map_err(|error| error.message)
}

#[test]
fn a_rule_with_kinds_and_an_external_user_parses() -> Result<(), String> {
    let extra =
        format!(r#", "item_kinds": ["function", "static_constant"], "external_users": [{USER}]"#);
    let parsed = read(&contract("3.16.0", &extra))?;
    let [Rule::UnusedPublic(rule)] = parsed.rules().as_slice() else {
        return Err("one unused_public rule".to_owned());
    };
    assert_eq!(rule.source().as_text(), "p");
    assert_eq!(
        rule.item_kinds(),
        &[PublicItemKind::Function, PublicItemKind::StaticConstant]
    );
    let [user] = rule.external_users().as_slice() else {
        return Err("one external user".to_owned());
    };
    assert_eq!(
        (user.symbol().as_str(), user.consumer().as_str()),
        ("p.a:f", "a plugin")
    );
    Ok(())
}

#[test]
fn each_malformed_rule_is_refused() {
    let no_name = r#", "external_users": [{"symbol": "p.a.f", "consumer": "c", "rationale": "r"}]"#;
    let refused = [
        (contract("3.15.0", ""), "3.16.0"),
        (contract("3.16.0", r#", "item_kinds": []"#), "non-empty"),
        (
            contract("3.16.0", r#", "item_kinds": ["method"]"#),
            "unknown kind",
        ),
        (
            contract("3.16.0", r#", "item_kinds": ["class", "class"]"#),
            "repeat",
        ),
        (contract("3.16.0", no_name), "module:Name"),
        (
            contract(
                "3.16.0",
                &format!(r#", "external_users": [{USER}, {USER}]"#),
            ),
            "repeat",
        ),
        (
            contract("3.16.0", r#", "external_users": [{"symbol": "p:f"}]"#),
            "fields",
        ),
    ];
    for (text, expected) in refused {
        let message = read(&text).err();
        assert!(
            message
                .as_ref()
                .is_some_and(|message| message.contains(expected)),
            "{expected}: {message:?} for {text}"
        );
    }
}
