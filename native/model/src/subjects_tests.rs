// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The subject check of `rule_subject_failures` (slice S4).

use archkeel_contract::{Contract, ParsedContract};

use super::{check, planned, Names, Subjects};

const HEAD: &str = r#""rationale": "r", "provenance": ["p"], "decided_by": "architect""#;

fn component(id: &str, packages: &str, extra: &str) -> String {
    format!(
        r#"{{"id": "{id}", "label": "{id}", "role": "component", "packages": {packages},
        "responsibilities": ["Own it."], "forbidden_responsibilities": [],
        "provenance": ["docs/a.md"]{extra}}}"#
    )
}

/// A contract of two components (`a` owns `x.a`, `b` owns `x.b`) and one rule.
fn contract(rule: &str, extra_a: &str) -> Option<Contract> {
    let text = format!(
        r#"{{"schema_version": "3.5.0", "components": [{}, {}], "rules": [{rule}]}}"#,
        component("a", r#"["x.a"]"#, extra_a),
        component("b", r#"["x.b"]"#, ""),
    );
    match archkeel_contract::parse(text.as_bytes()) {
        Ok(ParsedContract::Complete(contract)) => Some(contract),
        other => {
            assert_eq!(format!("{other:?}"), "", "the contract parses");
            None
        }
    }
}

fn subjects(rule: &str, modules: &[&str], builtins: &[String]) -> Option<Subjects> {
    subjects_with(rule, "", modules, builtins)
}

fn subjects_with(
    rule: &str,
    extra_a: &str,
    modules: &[&str],
    builtins: &[String],
) -> Option<Subjects> {
    let contract = contract(rule, extra_a)?;
    let subjects: Vec<&str> = modules
        .iter()
        .copied()
        .chain(planned(contract.components()))
        .collect();
    let names = Names {
        symbols: Vec::new(),
        targets: subjects.clone(),
        subjects,
        builtins,
    };
    Some(check(&contract.rules()[0], contract.components(), &names))
}

fn forbidden(fields: &str) -> String {
    format!(r#"{{"id": "F", "kind": "forbidden_dependency", {fields}, {HEAD}}}"#)
}

#[test]
fn a_forbidden_dependency_of_two_owned_packages_selects_the_whole_components() {
    let rule = forbidden(
        r#""source": "x.a", "target": "x.b", "include_type_checking": false, "allowed_sources": []"#,
    );
    // `a` also owns the exact module `y.m`: the component pair selects it.
    let exact = r#", "exact_modules": ["y.m"]"#;
    assert_eq!(
        subjects_with(&rule, exact, &["y.m", "x.b.k"], &[]),
        Some(Subjects::Found)
    );
    assert_eq!(
        subjects_with(&rule, "", &["y.m", "x.b.k"], &[]),
        Some(Subjects::Missing)
    );
}

#[test]
fn a_forbidden_dependency_with_an_exact_source_matches_only_that_module() {
    let rule = forbidden(
        r#""source": "x.a", "target": "x.b", "include_type_checking": false,
           "allowed_sources": [], "source_match": "exact""#,
    );
    assert_eq!(
        subjects(&rule, &["x.a.k", "x.b"], &[]),
        Some(Subjects::Missing)
    );
    assert_eq!(subjects(&rule, &["x.a", "x.b"], &[]), Some(Subjects::Found));
}

#[test]
fn a_builtin_or_namespace_target_has_no_target_side() {
    let rule = forbidden(
        r#""source": "x.a", "target": "fs", "include_type_checking": false, "allowed_sources": []"#,
    );
    assert_eq!(subjects(&rule, &["x.a"], &[]), Some(Subjects::Missing));
    assert_eq!(
        subjects(&rule, &["x.a"], &["fs".to_owned()]),
        Some(Subjects::Found)
    );
    let namespace = forbidden(
        r#""source": "x.a", "target": "fs", "include_type_checking": false,
           "allowed_sources": [], "target_kind": "import_namespace""#,
    );
    assert_eq!(subjects(&namespace, &["x.a"], &[]), Some(Subjects::Found));
}

#[test]
fn a_planned_module_is_a_subject() {
    let rule = format!(r#"{{"id": "S", "kind": "complete_assignment", "source": "x.c", {HEAD}}}"#);
    assert_eq!(subjects(&rule, &["x.a"], &[]), Some(Subjects::Missing));
    let planned = r#", "planned": ["x.c.later:Thing"]"#;
    assert_eq!(
        subjects_with(&rule, planned, &["x.a"], &[]),
        Some(Subjects::Found)
    );
}

#[test]
fn each_side_of_a_rule_must_match() {
    let allowed = format!(
        r#"{{"id": "A", "kind": "allowed_dependency", "source": "x.a", "target": "x.z", {HEAD}}}"#
    );
    assert_eq!(subjects(&allowed, &["x.a"], &[]), Some(Subjects::Missing));
    let external = format!(
        r#"{{"id": "E", "kind": "external_dependency_scope", "dependency": "d",
            "allowed_sources": ["x.a"], "exact_sources": ["x.z"], {HEAD}}}"#
    );
    assert_eq!(subjects(&external, &["x.a"], &[]), Some(Subjects::Missing));
    assert_eq!(
        subjects(&external, &["x.a", "x.z"], &[]),
        Some(Subjects::Found)
    );
    let sibling = format!(
        r#"{{"id": "P", "kind": "sibling_isolation", "members": ["x.z", "x.a"],
            "include_type_checking": false, {HEAD}}}"#
    );
    assert_eq!(subjects(&sibling, &["x.a"], &[]), Some(Subjects::Found));
    let layout = format!(
        r#"{{"id": "L", "kind": "root_layout", "root": "x", "allowed_children": [], {HEAD}}}"#
    );
    assert_eq!(subjects(&layout, &["xa"], &[]), Some(Subjects::Missing));
}

#[test]
fn a_rule_without_a_side_always_finds_its_subjects() {
    let requires = format!(
        r#"{{"id": "R", "kind": "complete_requires", "include_type_checking": false, {HEAD}}}"#
    );
    assert_eq!(subjects(&requires, &[], &[]), Some(Subjects::Found));
}

/// AD-385: in a mount the source side reads the domain of the mount and the target side every
/// module (`rule_subject_failures` with `target_module_names`).
#[test]
fn a_target_side_reads_every_module_and_a_source_side_only_the_domain() {
    let rule = forbidden(
        r#""source": "x.a", "target": "x.b", "include_type_checking": false, "allowed_sources": []"#,
    );
    let Some(contract) = contract(&rule, "") else {
        assert_eq!("the contract must parse", "loaded");
        return;
    };
    let check_with = |subjects: Vec<&str>, targets: Vec<&str>| {
        let names = Names {
            symbols: Vec::new(),
            subjects,
            targets,
            builtins: &[],
        };
        check(&contract.rules()[0], contract.components(), &names)
    };
    assert_eq!(
        check_with(vec!["x.a.m"], vec!["x.a.m", "x.b.m"]),
        Subjects::Found
    );
    assert_eq!(
        check_with(vec!["x.a.m", "x.b.m"], vec!["x.a.m"]),
        Subjects::Missing
    );
    assert_eq!(
        check_with(vec!["x.b.m"], vec!["x.a.m", "x.b.m"]),
        Subjects::Missing
    );
}
