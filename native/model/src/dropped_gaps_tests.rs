// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The rules that a dropped pair gap holds (AD-418).

use archkeel_contract::{ParsedContract, Rule};

use super::holds;
use crate::pair_gaps::{reads, PairGap};

const HEAD: &str = r#""rationale": "r", "provenance": ["p"], "decided_by": "architect""#;

/// The one rule of a contract of two components: `a` owns `x.a` and `b` owns `x.b`.
fn rule(kind_and_fields: &str) -> Option<Rule> {
    let component = |id: &str| {
        format!(
            r#"{{"id": "{id}", "label": "{id}", "role": "component", "packages": ["x.{id}"],
            "responsibilities": ["Own it."], "forbidden_responsibilities": [],
            "provenance": ["docs/a.md"]}}"#
        )
    };
    let text = format!(
        r#"{{"schema_version": "3.5.0", "components": [{}, {}],
        "rules": [{{"id": "R", {kind_and_fields}, {HEAD}}}]}}"#,
        component("a"),
        component("b"),
    );
    match archkeel_contract::parse(text.as_bytes()) {
        Ok(ParsedContract::Complete(contract)) => contract.rules().first().cloned(),
        other => {
            assert_eq!(format!("{other:?}"), "", "the contract parses");
            None
        }
    }
}

fn gap(observed: bool, external: bool) -> PairGap {
    PairGap {
        source: "x.a.m".to_owned(),
        target: "x.b.n".to_owned(),
        observed,
        owned: [true, true],
        target_external: external,
    }
}

/// True when the dropped gap holds the rule, read with the components of its contract.
fn held(gap: &PairGap, rule: &Rule) -> bool {
    holds(gap, rule, &reads(rule, &[]))
}

const CYCLES: &str = r#""kind": "no_component_cycles", "level": "module""#;
const REQUIRES: &str = r#""kind": "complete_requires""#;

#[test]
fn a_dropped_gap_between_two_seen_modules_holds_no_cycle_and_no_requires_rule() {
    // The drop rule proves both: no cycle through the edge, a plain `requires` or one component.
    for fields in [CYCLES, REQUIRES, r#""kind": "no_component_cycles""#] {
        let Some(rule) = rule(fields) else { return };
        assert!(!held(&gap(true, true), &rule), "{fields}");
        // The kept reading of these kinds is every edge.
        assert!(gap(true, true).holds(&reads(&rule, &[])), "{fields}");
    }
}

#[test]
fn a_dropped_gap_to_a_module_that_the_scan_did_not_see_holds_the_cycle_and_requires_rules() {
    for fields in [CYCLES, REQUIRES] {
        let Some(rule) = rule(fields) else { return };
        assert!(held(&gap(false, false), &rule), "{fields}");
    }
}

#[test]
fn a_dropped_gap_into_a_module_with_an_external_import_holds_the_external_rules() {
    // A hidden edge into a module that imports an external package can re-export it.
    for fields in [
        r#""kind": "complete_external_scope", "source": "x""#,
        r#""kind": "external_dependency_scope", "dependency": "p", "allowed_sources": ["x.b"]"#,
    ] {
        let Some(rule) = rule(fields) else { return };
        assert!(held(&gap(true, true), &rule), "{fields}");
        assert!(!held(&gap(true, false), &rule), "{fields}");
    }
}

#[test]
fn a_dropped_gap_holds_a_forbidden_rule_whose_sides_it_joins_and_no_module_set() {
    let forward = r#""kind": "forbidden_dependency", "source": "x.a", "target": "x.b",
        "include_type_checking": true"#;
    let backward = r#""kind": "forbidden_dependency", "source": "x.b", "target": "x.a",
        "include_type_checking": true"#;
    let (Some(forward), Some(backward), Some(modules)) = (
        rule(forward),
        rule(backward),
        rule(r#""kind": "complete_assignment", "source": "x""#),
    ) else {
        return;
    };
    assert!(held(&gap(true, false), &forward));
    assert!(!held(&gap(true, false), &backward));
    assert!(!held(&gap(true, true), &modules));
}
