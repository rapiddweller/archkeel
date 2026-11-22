// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

use crate::contract::parse_file;
use crate::document::Contract;

/// A contract older than 3.20.0 spells the key `door_reach` and the field `door` (AD-1054).
fn contract(version: &str, reach: &str) -> String {
    let (key, reach) = if version == "3.20.0" {
        ("trojan_horse_reach", reach.to_string())
    } else {
        ("door_reach", reach.replace("\"trojan_horse\"", "\"door\""))
    };
    format!(
        r#"{{"schema_version": "{version}", "components": [], "rules": [],
        "declarations": {{"{key}": [{reach}]}}}}"#
    )
}

fn reach(extra: &str) -> String {
    format!(
        r#"{{"id": "D-1", "module": "p.a", "trojan_horse": "eval", "loads": ["p.b", "json"],
        "rationale": "The text is a formula.", "provenance": ["d.md"]{extra}}}"#
    )
}

fn read(text: &str) -> Result<Contract, String> {
    parse_file(text.as_bytes()).map_err(|error| error.message)
}

#[test]
fn a_trojan_horse_reach_with_a_line_parses_and_keeps_its_fields() -> Result<(), String> {
    let parsed = read(&contract(
        "3.15.0",
        &reach(r#", "line": 12, "changes": ["p.c"]"#),
    ))?;
    let declarations = parsed.declarations().as_ref().ok_or("declarations")?;
    let [trojan_horse] = declarations.trojan_horse_reach().as_slice() else {
        return Err("one trojan horse reach".to_owned());
    };
    assert_eq!(trojan_horse.id().as_text(), "D-1");
    assert_eq!(trojan_horse.module().as_text(), "p.a");
    assert_eq!(trojan_horse.trojan_horse(), "eval");
    assert_eq!(*trojan_horse.line(), Some(12));
    assert_eq!(trojan_horse.scope(), &None);
    let loads: Vec<&str> = trojan_horse
        .loads()
        .iter()
        .flatten()
        .map(|p| p.as_text())
        .collect();
    assert_eq!(loads, ["p.b", "json"]);
    let changes: Vec<&str> = trojan_horse.changes().iter().map(|p| p.as_text()).collect();
    assert_eq!(changes, ["p.c"]);
    Ok(())
}

#[test]
fn a_scope_selector_and_the_module_level_parse() -> Result<(), String> {
    read(&contract("3.15.0", &reach(r#", "scope": "Loader.run""#)))?;
    read(&contract("3.15.0", &reach(r#", "scope": """#)))?;
    Ok(())
}

#[test]
fn each_malformed_trojan_horse_reach_is_refused() {
    let refused = [
        (contract("3.14.0", &reach(r#", "line": 1"#)), "3.15.0"),
        (contract("3.15.0", &reach("")), "by line or scope"),
        (contract("3.15.0", &reach(r#", "line": 0"#)), "positive"),
        (contract("3.15.0", &reach(r#", "scope": "a b""#)), "scope"),
        (
            contract("3.15.0", &reach(r#", "line": 1, "changes": ["p-x"]"#)),
            "dotted",
        ),
        (
            contract("3.15.0", &reach(r#", "line": 1, "extra": 1"#)),
            "fields mismatch",
        ),
        (
            contract(
                "3.15.0",
                &format!("{}, {}", reach(r#", "line": 1"#), reach(r#", "line": 2"#)),
            ),
            "duplicate contract ID",
        ),
    ];
    for (text, word) in refused {
        let message = read(&text).err().unwrap_or_default();
        assert!(message.contains(word), "{word}: {message}");
    }
}

#[test]
fn the_canonical_bytes_keep_the_trojan_horse_reach() -> Result<(), String> {
    let parsed = read(&contract("3.15.0", &reach(r#", "line": 3"#)))?;
    let bytes = String::from_utf8(crate::canonical::canonical_bytes(&parsed))
        .map_err(|error| error.to_string())?;
    assert!(bytes.contains("\"trojan_horse_reach\""), "{bytes}");
    assert!(bytes.contains("\"line\": 3"), "{bytes}");
    Ok(())
}

#[test]
fn a_constant_bound_is_versioned_and_round_trips_without_a_free_list() -> Result<(), String> {
    let bound = r#"{"constant":"app.registry:MODULES","template":"app.{}.interface",
                     "call":"importlib.import_module(name)"}"#;
    let extra = format!(r#", "line": 7, "loads_from": {bound}"#);
    let raw = reach(&extra);
    let only_bound = raw
        .replace(r#""loads": ["p.b", "json"],"#, "")
        .replace(r#""trojan_horse": "eval""#, r#""trojan_horse": "loader""#);
    assert_ne!(raw, only_bound);
    let parsed = read(&contract("3.18.0", &only_bound))?;
    let bytes = String::from_utf8(crate::canonical::canonical_bytes(&parsed))
        .map_err(|error| error.to_string())?;
    assert!(bytes.contains("\"loads_from\"") && !bytes.contains("\"loads\""));
    read(&bytes)?;
    assert!(read(&contract("3.17.0", &only_bound)).is_err());
    assert!(read(&contract("3.18.0", &raw)).is_err());
    Ok(())
}

#[test]
fn a_site_name_and_a_count_need_contract_3_20_and_one_key() -> Result<(), String> {
    let named = reach(r#", "name": "pickle.load", "count": 2, "scope": """#)
        .replace(r#""trojan_horse": "eval","#, "");
    assert!(
        named.contains("pickle.load") && !named.contains("\"trojan_horse\""),
        "{named}"
    );
    let parsed = read(&contract("3.20.0", &named))?;
    let bytes = String::from_utf8(crate::canonical::canonical_bytes(&parsed))
        .map_err(|error| error.to_string())?;
    assert!(bytes.contains("\"name\": \"pickle.load\"") && bytes.contains("\"count\": 2"));
    read(&bytes)?;
    let old = read(&contract("3.19.0", &named)).err().unwrap_or_default();
    assert!(old.contains("3.20.0"), "{old}");
    let alone = named.replace(r#", "scope": """#, "");
    let message = read(&contract("3.20.0", &alone)).err().unwrap_or_default();
    assert!(message.contains("by line or scope"), "{message}");
    let both = reach(r#", "name": "pickle.load""#);
    let message = read(&contract("3.20.0", &both)).err().unwrap_or_default();
    assert!(message.contains("by trojan_horse or by name"), "{message}");
    let neither = reach(r#", "line": 1"#).replace(r#""trojan_horse": "eval","#, "");
    let message = read(&contract("3.20.0", &neither))
        .err()
        .unwrap_or_default();
    assert!(message.contains("by trojan_horse or by name"), "{message}");
    let zero = named.replace(r#""count": 2"#, r#""count": 0"#);
    assert!(read(&contract("3.20.0", &zero)).is_err());
    Ok(())
}
