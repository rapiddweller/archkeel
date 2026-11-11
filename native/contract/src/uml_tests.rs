// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

use crate::canonical::canonical_bytes;
use crate::contract::parse_file as parse;
use crate::error::ErrorKind;

const COMPONENT: &str = r#"{"id": "C-A", "label": "a", "role": "component", "packages": ["p.a"],
  "responsibilities": ["Own a."], "forbidden_responsibilities": [], "provenance": ["d.md"]}"#;

fn with_uml(entities: &str) -> String {
    format!(
        r#"{{"schema_version": "2.2.0", "components": [{COMPONENT}], "rules": [],
        "declarations": {{"uml": {{"schema_version": "1.1.0", "entities": [{entities}]}}}}}}"#
    )
}

fn class(id: &str, presence: &str) -> String {
    format!(
        r#"{{"id": "{id}", "kind": "class", "qualified_name": "p.a.K", "language": "python",
        "presence": "{presence}", "responsibilities": ["Own K."], "provenance": ["d.md"]}}"#
    )
}

#[test]
fn a_uml_target_parses_and_keeps_its_nulls_in_the_canonical_bytes() -> Result<(), String> {
    let contract = parse(with_uml(&class("E-K", "planned")).as_bytes()).map_err(|e| e.message)?;
    let written = String::from_utf8_lossy(&canonical_bytes(&contract)).into_owned();
    assert!(written.contains(r#""parent_id": null"#), "{written}");
    assert!(written.contains(r#""capabilities": []"#), "{written}");
    assert!(!written.contains("facade_budgets"), "{written}");
    Ok(())
}

#[test]
fn a_repeated_planned_entity_is_invalid() {
    let entities = format!("{}, {}", class("E-K", "planned"), class("E-K2", "planned"));
    let kind = parse(with_uml(&entities).as_bytes())
        .err()
        .map(|error| error.kind);
    assert_eq!(kind, Some(ErrorKind::Invalid));
}

#[test]
fn a_bare_reference_links_and_a_reference_with_constraints_is_invalid() {
    let reference = r#"{"id": "E-R", "kind": "class", "qualified_name": "p.a.K",
        "language": "python", "presence": "referenced", "provenance": ["e.md"]}"#;
    let linked = format!("{}, {reference}", class("E-K", "planned"));
    assert!(parse(with_uml(&linked).as_bytes()).is_ok());
    let constrained = linked.replace(
        r#""provenance": ["e.md"]"#,
        r#""provenance": ["e.md"], "modifiers": ["static"]"#,
    );
    let kind = parse(with_uml(&constrained).as_bytes())
        .err()
        .map(|error| error.kind);
    assert_eq!(kind, Some(ErrorKind::Invalid));
}
