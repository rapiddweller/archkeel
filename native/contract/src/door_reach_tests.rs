// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

use crate::contract::parse_file;
use crate::document::Contract;

fn contract(version: &str, reach: &str) -> String {
    format!(
        r#"{{"schema_version": "{version}", "components": [], "rules": [],
        "declarations": {{"door_reach": [{reach}]}}}}"#
    )
}

fn reach(extra: &str) -> String {
    format!(
        r#"{{"id": "D-1", "module": "p.a", "door": "eval", "loads": ["p.b", "json"],
        "rationale": "The text is a formula.", "provenance": ["d.md"]{extra}}}"#
    )
}

fn read(text: &str) -> Result<Contract, String> {
    parse_file(text.as_bytes()).map_err(|error| error.message)
}

#[test]
fn a_door_reach_with_a_line_parses_and_keeps_its_fields() -> Result<(), String> {
    let parsed = read(&contract(
        "3.15.0",
        &reach(r#", "line": 12, "changes": ["p.c"]"#),
    ))?;
    let declarations = parsed.declarations().as_ref().ok_or("declarations")?;
    let [door] = declarations.door_reach().as_slice() else {
        return Err("one door reach".to_owned());
    };
    assert_eq!(door.id().as_text(), "D-1");
    assert_eq!(door.module().as_text(), "p.a");
    assert_eq!(door.door(), "eval");
    assert_eq!(*door.line(), Some(12));
    assert_eq!(door.scope(), &None);
    let loads: Vec<&str> = door.loads().iter().flatten().map(|p| p.as_text()).collect();
    assert_eq!(loads, ["p.b", "json"]);
    let changes: Vec<&str> = door.changes().iter().map(|p| p.as_text()).collect();
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
fn each_malformed_door_reach_is_refused() {
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
fn the_canonical_bytes_keep_the_door_reach() -> Result<(), String> {
    let parsed = read(&contract("3.15.0", &reach(r#", "line": 3"#)))?;
    let bytes = String::from_utf8(crate::canonical::canonical_bytes(&parsed))
        .map_err(|error| error.to_string())?;
    assert!(bytes.contains("\"door_reach\""), "{bytes}");
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
        .replace(r#""door": "eval""#, r#""door": "loader""#);
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
