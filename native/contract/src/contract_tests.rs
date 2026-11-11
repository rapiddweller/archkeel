// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

use super::parse_file as parse;
use crate::canonical::{canonical_bytes, canonical_digest};
use crate::error::ErrorKind;
use crate::model::{CycleLevel, SelectorMatch};
use crate::rule::Rule;

const COMPONENT: &str = r#"{"id": "C-A", "label": "a", "role": "component", "packages": ["p.a"],
  "responsibilities": ["Own a."], "forbidden_responsibilities": [], "provenance": ["d.md"],
  "requires": [{"component": "a", "rationale": "Self."}]}"#;

fn contract(version: &str, rules: &str) -> String {
    format!(r#"{{"schema_version": "{version}", "components": [{COMPONENT}], "rules": [{rules}]}}"#)
}

fn rule(kind: &str, extra: &str) -> String {
    format!(
        r#"{{"id": "R", "kind": "{kind}", "rationale": "Why.", "provenance": ["d.md"],
        "decided_by": "architect"{extra}}}"#
    )
}

fn read_contract(text: &str) -> Result<crate::document::Contract, String> {
    parse(text.as_bytes()).map_err(|error| error.message)
}

fn kind_of(text: &str) -> Option<ErrorKind> {
    parse(text.as_bytes()).err().map(|error| error.kind)
}

#[test]
fn a_minimal_contract_parses_and_writes_the_python_canonical_bytes() -> Result<(), String> {
    let text = contract("2.1.0", &rule("complete_requires", ""));
    let parsed = read_contract(&text)?;
    let expected = r#"{
  "schema_version": "2.1.0",
  "components": [
    {
      "id": "C-A",
      "label": "a",
      "role": "component",
      "packages": [
        "p.a"
      ],
      "responsibilities": [
        "Own a."
      ],
      "forbidden_responsibilities": [],
      "provenance": [
        "d.md"
      ],
      "requires": [
        {
          "component": "a",
          "rationale": "Self.",
          "through": []
        }
      ]
    }
  ],
  "rules": [
    {
      "id": "R",
      "kind": "complete_requires",
      "rationale": "Why.",
      "provenance": [
        "d.md"
      ],
      "decided_by": "architect",
      "include_type_checking": true
    }
  ]
}
"#;
    assert_eq!(String::from_utf8_lossy(&canonical_bytes(&parsed)), expected);
    assert_eq!(parsed.digest.0.len(), 64);
    assert_ne!(parsed.digest, canonical_digest(&parsed));
    Ok(())
}

#[test]
fn a_repeated_key_is_refused_also_inside_a_rule() {
    let text = contract("2.1.0", &rule("complete_requires", r#", "id": "R2""#));
    assert_eq!(kind_of(&text), Some(ErrorKind::DuplicateKey));
}

#[test]
fn any_unknown_or_malformed_version_is_a_version_error() {
    for version in [r#""9.9.9""#, "2", "null"] {
        let text = format!(r#"{{"schema_version": {version}, "components": [], "rules": []}}"#);
        assert_eq!(kind_of(&text), Some(ErrorKind::Version), "{version}");
    }
    let missing_rules = r#"{"schema_version": "9.9.9", "components": []}"#;
    assert_eq!(kind_of(missing_rules), Some(ErrorKind::Invalid));
}

#[test]
fn a_repeated_label_and_an_unknown_requires_label_are_input_errors() {
    let twin = COMPONENT.replace("C-A", "C-B");
    let repeated = format!(
        r#"{{"schema_version": "2.1.0", "components": [{COMPONENT}, {twin}], "rules": []}}"#
    );
    assert_eq!(kind_of(&repeated), Some(ErrorKind::Input));
    let stray = contract("2.1.0", "").replace(r#""component": "a""#, r#""component": "b""#);
    assert_eq!(kind_of(&stray), Some(ErrorKind::Input));
}

#[test]
fn an_earlier_invalid_component_wins_over_a_later_input_error() {
    let broken = COMPONENT.replace(r#""role": "component""#, r#""role": "nothing""#);
    let text = format!(
        r#"{{"schema_version": "2.1.0", "components": [{broken}, {COMPONENT}], "rules": []}}"#
    );
    assert_eq!(kind_of(&text), Some(ErrorKind::Invalid));
}

#[test]
fn declarations_and_a_python_only_rule_parse() {
    let declared =
        r#"{"schema_version": "2.1.0", "components": [], "rules": [], "declarations": {}}"#;
    assert_eq!(kind_of(declared), None);
    let null =
        r#"{"schema_version": "2.1.0", "components": [], "rules": [], "declarations": null}"#;
    assert_eq!(kind_of(null), None);
    let call_owner = contract(
        "3.7.0",
        &rule("call_owner", r#", "source": "a", "target": "b""#),
    );
    assert_eq!(kind_of(&call_owner), None);
}

#[test]
fn a_version_gate_refuses_a_python_only_rule_of_an_older_contract() {
    let early = contract(
        "3.6.0",
        &rule("call_owner", r#", "source": "a", "target": "b""#),
    );
    assert_eq!(kind_of(&early), Some(ErrorKind::Invalid));
    let selector = contract(
        "3.3.0",
        &rule("forbidden_dependency", r#", "source_match": "exact""#),
    );
    assert_eq!(kind_of(&selector), Some(ErrorKind::Invalid));
}

#[test]
fn defaults_are_typed_and_left_out_of_the_canonical_bytes() -> Result<(), String> {
    let fields = r#", "source": "p.a", "target": "p.b", "include_type_checking": false"#;
    let text = contract("3.4.0", &rule("forbidden_dependency", fields));
    let parsed = read_contract(&text)?;
    let Some(Rule::ForbiddenDependency(found)) = parsed.rules.first() else {
        return Err(format!("{:?}", parsed.rules));
    };
    assert_eq!(found.source_match, SelectorMatch::Prefix);
    let written = String::from_utf8_lossy(&canonical_bytes(&parsed)).into_owned();
    assert!(!written.contains("source_match"), "{written}");
    let cycles = contract(
        "2.1.0",
        &rule("no_component_cycles", r#", "level": "component""#),
    );
    let parsed = read_contract(&cycles)?;
    let Some(Rule::NoComponentCycles(found)) = parsed.rules.first() else {
        return Err(format!("{:?}", parsed.rules));
    };
    assert_eq!(found.level, CycleLevel::Component);
    assert!(!String::from_utf8_lossy(&canonical_bytes(&parsed)).contains("level"));
    Ok(())
}

#[test]
fn python_white_space_and_identifiers_are_read_as_python_reads_them() {
    let blank = contract("2.1.0", &rule("complete_requires", "")).replace("Why.", "\\u001c");
    assert_eq!(kind_of(&blank), Some(ErrorKind::Invalid));
    let symbol = r#", "source": "p.a", "target": "p.b", "include_type_checking": true, "target_symbol": "été""#;
    assert_eq!(
        kind_of(&contract("2.1.0", &rule("forbidden_dependency", symbol))),
        None
    );
}

#[test]
fn a_contract_with_a_mount_needs_its_tree_and_names_the_mount_by_type() -> Result<(), String> {
    use crate::document::ParsedContract;
    let plain = contract("2.1.0", "");
    assert!(matches!(
        super::parse(plain.as_bytes()),
        Ok(ParsedContract::Complete(_))
    ));
    let mounted = plain.replace(
        r#""packages": ["p.a"]"#,
        r#""packages": ["p.a"], "inside": "inner.json""#,
    );
    let Ok(ParsedContract::NeedsTree(tree)) = super::parse(mounted.as_bytes()) else {
        return Err("a mount must need its tree".to_owned());
    };
    let mount = tree.mounts().first().ok_or("one mount")?;
    assert_eq!(
        (mount.component().as_text(), mount.path().as_text()),
        ("C-A", "inner.json")
    );
    Ok(())
}
