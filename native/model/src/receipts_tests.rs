// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The receipt scopes of `complete_requires` (review S1 (b) of #1084). Through the evaluator the
//! check is not reachable today: each selector kind is a certain profile limit of every
//! store-accepted profile (`limits.rs`), so the scope state stops first. The check stays, so a
//! profile that lifts a limit cannot pass `complete_requires` without the receipt scope.

use archkeel_contract::{parse, ParsedContract, Rule};

fn rules(json: &str) -> Vec<Rule> {
    let text = format!(
        r#"{{"schema_version": "3.11.0", "components": [{{"id": "COMP-A", "label": "a",
        "role": "component", "packages": ["app"], "responsibilities": ["Own it."],
        "forbidden_responsibilities": [], "provenance": ["docs/a.md"], "requires": [],
        "decided_by": "architect"}}], "rules": [{json}]}}"#
    );
    match parse(text.as_bytes()) {
        Ok(ParsedContract::Complete(contract)) => contract.rules().to_vec(),
        other => {
            assert!(
                matches!(other, Ok(ParsedContract::Complete(_))),
                "{other:?}"
            );
            Vec::new()
        }
    }
}

const HEAD: &str =
    r#""rationale": "A test.", "provenance": ["docs/a.md"], "decided_by": "architect""#;

#[test]
fn a_construct_rule_with_a_selector_adds_a_receipt_scope_and_one_without_does_not() {
    let selector = format!(
        r#"{{"id": "SEL", "kind": "forbidden_construct", "source": "app", "constructs": ["eval"],
        "selector": {{"receiver": "Order", "member": "id", "role": "read"}}, {HEAD}}}"#
    );
    let plain = format!(
        r#"{{"id": "PLAIN", "kind": "forbidden_construct", "source": "app",
        "constructs": ["eval"], {HEAD}}}"#
    );
    let requires = format!(r#"{{"id": "REQ", "kind": "complete_requires", {HEAD}}}"#);
    for (json, expected) in [(selector, true), (plain, false), (requires, false)] {
        let found = rules(&json);
        assert_eq!(found.len(), 1, "{json}");
        assert!(
            found
                .iter()
                .all(|rule| super::selector_source(rule) == expected),
            "{json}"
        );
    }
}
