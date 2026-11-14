// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The symbol selector that each rule reads (AD-482).

use archkeel_contract::{Contract, ParsedContract};

use super::symbol_reader;

const HEAD: &str = r#""rationale": "r", "provenance": ["p"], "decided_by": "architect""#;

fn component(id: &str, packages: &str, extra: &str) -> String {
    format!(
        r#"{{"id": "{id}", "label": "{id}", "role": "component", "packages": {packages},
        "responsibilities": ["Own it."], "forbidden_responsibilities": [],
        "provenance": ["docs/a.md"]{extra}}}"#
    )
}

/// A contract of two components (`a` owns `x.a`, `b` owns `x.b`) and its rules.
fn contract(rules: &[&str], extra_a: &str, extra_b: &str) -> Option<Contract> {
    let text = format!(
        r#"{{"schema_version": "3.5.0", "components": [{}, {}], "rules": [{}]}}"#,
        component("a", r#"["x.a"]"#, extra_a),
        component("b", r#"["x.b"]"#, extra_b),
        rules.join(", "),
    );
    match archkeel_contract::parse(text.as_bytes()) {
        Ok(ParsedContract::Complete(contract)) => Some(contract),
        other => {
            assert_eq!(format!("{other:?}"), "", "the contract parses");
            None
        }
    }
}

fn forbid(id: &str, symbol: &str) -> String {
    format!(
        r#"{{"id": "{id}", "kind": "forbidden_dependency", "source": "x.a", "target": "x.b",
        "include_type_checking": true{symbol}, {HEAD}}}"#
    )
}

fn kind(id: &str, kind: &str) -> String {
    format!(r#"{{"id": "{id}", "kind": "{kind}", {HEAD}}}"#)
}

/// The reader of each rule of the contract, by rule id.
fn readers(rules: &[&str], extra_a: &str, extra_b: &str) -> Vec<(String, Option<String>)> {
    let Some(contract) = contract(rules, extra_a, extra_b) else {
        return Vec::new();
    };
    contract
        .rules()
        .iter()
        .map(|rule| {
            let id = archkeel_contract::head_of(rule).id().as_text().to_owned();
            (id, symbol_reader(&contract, rule))
        })
        .collect()
}

fn pairs(expected: &[(&str, Option<&str>)]) -> Vec<(String, Option<String>)> {
    expected
        .iter()
        .map(|(id, reader)| ((*id).to_owned(), reader.map(str::to_owned)))
        .collect()
}

#[test]
fn a_target_symbol_holds_its_own_rule_and_each_interface_rule() {
    let rules = [
        &forbid("SYMBOL", r#", "target_symbol": "S""#),
        &forbid("MODULE", ""),
        &kind("REQUIRES", "complete_requires"),
        &kind("BOUNDARY", "interface_boundary"),
        &kind("CYCLES", "no_component_cycles"),
    ];
    assert_eq!(
        readers(&rules.map(String::as_str), "", ""),
        pairs(&[
            ("SYMBOL", Some("SYMBOL")),
            ("MODULE", None),
            ("REQUIRES", None),
            ("BOUNDARY", Some("SYMBOL")),
            ("CYCLES", None),
        ])
    );
}

#[test]
fn a_symbol_port_holds_each_complete_requires_rule_only() {
    let rules = [
        &forbid("MODULE", ""),
        &kind("REQUIRES", "complete_requires"),
        &kind("BOUNDARY", "interface_boundary"),
    ];
    let port = r#", "requires": [{"component": "b", "rationale": "r", "through": ["x.b:S"]}]"#;
    let module = r#", "requires": [{"component": "b", "rationale": "r", "through": ["x.b"]}]"#;
    let rules = rules.map(String::as_str);
    assert_eq!(
        readers(&rules, port, ""),
        pairs(&[
            ("MODULE", None),
            ("REQUIRES", Some("a")),
            ("BOUNDARY", None)
        ])
    );
    assert!(readers(&rules, module, "").iter().all(|(_, r)| r.is_none()));
}

#[test]
fn a_symbol_public_entry_holds_each_interface_rule_only() {
    let rules = [
        &forbid("MODULE", ""),
        &kind("REQUIRES", "complete_requires"),
        &kind("BOUNDARY", "interface_boundary"),
    ];
    let rules = rules.map(String::as_str);
    assert_eq!(
        readers(&rules, "", r#", "public": ["x.b:S"]"#),
        pairs(&[
            ("MODULE", None),
            ("REQUIRES", None),
            ("BOUNDARY", Some("b"))
        ])
    );
    let module = readers(&rules, "", r#", "public": ["x.b"]"#);
    assert!(module.iter().all(|(_, r)| r.is_none()));
}
