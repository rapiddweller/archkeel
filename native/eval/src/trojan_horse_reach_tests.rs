// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The declared reach of a trojan horse site (AD-664), over the frozen H-typescript reply with its scan
//! root `src`. A trojan horse gap in `domain.index` states `every_module`. Without a declaration it holds
//! each rule but the rules of the files. A matched declaration lets the rules decide, and each
//! PASS that the trojan horse would hold names the declaration; a declared load into `data` is a real
//! edge and breaks DOMAIN-NO-DATA; a declaration that matches no trojan horse is a problem and changes
//! nothing.

use std::collections::BTreeMap;

use archkeel_model::{Cause, Graph, Model, Needs, Reason, TrojanHorseProblem, Verdict};
use serde_json::{json, Value};

use crate::evaluate;
use crate::gap_scope_tests::{rooted, INDEX, LOCAL, PAGE};
use crate::tests::{contract, reply};

const ID: &str = "UNKNOWN-00000000000000dd";

/// The rules of the fixture contract that read no edge and no code of a module.
const FILES_ONLY: [&str; 2] = ["LAYOUT", "ASSIGNMENT"];

/// A trojan horse gap `id` of `domain.index` with the trojan horse `site`.
fn trojan_horse_gap(id: &str, site: Value) -> Value {
    json!({
        "id": id, "evidence_class": "UNKNOWN", "area": "source",
        "kind": "source_resolution_gap", "title": "site", "subjects": [INDEX],
        "evidence_ids": [], "fact_ids": [], "rule_ids": [], "provenance": [],
        "data": {"reason": "site", "module": INDEX, "resolution_dimension": "imports",
                 "effect": "every_module", "trojan_horse": site}
    })
}

/// The trojan horse gaps `gaps` in the coverage and the unknowns of the reply.
fn trojan_horses(reply: &mut Value, gaps: Vec<Value>) {
    reply["facts"]["sections"][1]["records"] = json!(gaps.clone());
    reply["facts"]["coverage"]["gaps"] = json!(gaps);
    reply["facts"]["coverage"]["full_scope"] = json!(false);
}

/// A trojan horse gap of `domain.index` at line 7 with the form `eval`.
fn trojan_horse(reply: &mut Value) {
    trojan_horses(
        reply,
        vec![trojan_horse_gap(ID, json!({"form": "eval", "line": 7}))],
    );
}

/// The problems with the list of the sites of an unmatched declaration left out.
fn plain(problems: &[(String, TrojanHorseProblem)]) -> Vec<(String, TrojanHorseProblem)> {
    problems
        .iter()
        .map(|(id, problem)| match problem {
            TrojanHorseProblem::Unmatched(_) => {
                (id.clone(), TrojanHorseProblem::Unmatched(String::new()))
            }
            other => (id.clone(), other.clone()),
        })
        .collect()
}

/// A declaration of the trojan horse at `site` (extra fields) that loads `loads`.
fn declared(id: &str, site: Value, loads: &[&str]) -> Value {
    let mut item = json!({"id": id, "module": INDEX, "trojan_horse": "eval", "loads": loads,
                          "rationale": "The text is a formula.", "provenance": ["d.md"]});
    for (key, value) in site.as_object().into_iter().flatten() {
        item[key] = value.clone();
    }
    item
}

/// What one run gives: the verdict and reason of each rule, the run, the applied declaration ids,
/// the problems and the declarations that each PASS assumes.
struct Found {
    rules: BTreeMap<String, (&'static str, Option<Reason>)>,
    run: Result<(), Reason>,
    applied: Vec<String>,
    problems: Vec<(String, TrojanHorseProblem)>,
    assumed: BTreeMap<String, Vec<String>>,
}

fn run(declarations: Vec<Value>) -> Found {
    run_with(declarations, trojan_horse)
}

fn run_with(declarations: Vec<Value>, reply_change: impl FnOnce(&mut Value)) -> Found {
    let declarations_of = declarations.clone();
    let contract = contract(move |value: &mut Value| {
        value["schema_version"] = json!("3.20.0");
        value["declarations"] = json!({"trojan_horse_reach": declarations_of});
    })
    .expect("the contract parses");
    let reply = reply(reply_change).expect("the reply");
    let trojan_horses = contract
        .declarations()
        .as_ref()
        .map(|d| d.trojan_horse_reach().clone())
        .unwrap_or_default();
    let needs = Needs::default().with_trojan_horses(trojan_horses);
    let graph = Graph::derive_for(&reply, rooted(), &needs).expect("the graph");
    let model = Model::of(&contract, graph).expect("the model");
    let mut rules = BTreeMap::new();
    let mut assumed = BTreeMap::new();
    for outcome in evaluate(&model) {
        let Some(decision) = outcome.decision() else {
            continue;
        };
        let word = match decision.verdict() {
            Verdict::Pass(_) => "PASS",
            Verdict::Fail => "FAIL",
            Verdict::Unknown => "UNKNOWN",
        };
        let rule = model
            .contract()
            .rules()
            .iter()
            .find(|rule| archkeel_contract::head_of(rule).id().as_text() == outcome.rule())
            .expect("the rule");
        // The trojan horse premises of the rule (AD-764), as the ids of their applied declarations.
        let premised: Vec<String> = archkeel_model::rule_premises(&model, rule)
            .into_iter()
            .filter(|p| p.kind == archkeel_model::PremiseKind::TrojanHorseReach)
            .map(|p| p.subject)
            .collect();
        let applied = model.graph().trojan_horses().applied().iter();
        let sites: Vec<String> = applied
            .filter(|d| premised.contains(&archkeel_model::Applied::site(d)))
            .map(|d| d.id.clone())
            .collect();
        if word == "PASS" && !sites.is_empty() {
            assumed.insert(outcome.rule().to_owned(), sites);
        }
        rules.insert(
            outcome.rule().to_owned(),
            (word, decision.reason().cloned()),
        );
    }
    let trojan_horses = model.graph().trojan_horses();
    Found {
        rules,
        run: model.scope(|scope| scope.run()),
        applied: trojan_horses
            .applied()
            .iter()
            .map(|d| d.id.clone())
            .collect(),
        problems: trojan_horses
            .problems()
            .iter()
            .map(|(_, id, problem)| (id.clone(), problem.clone()))
            .collect(),
        assumed,
    }
}

fn word(found: &Found, rule: &str) -> &'static str {
    found.rules.get(rule).map_or("", |(word, _)| *word)
}

/// Each rule but the rules of the files is UNKNOWN because the trojan horse gap holds it.
fn assert_held_by_trojan_horse(found: &Found) {
    assert_eq!(found.rules.len(), 9, "each rule has a verdict");
    for (rule, (word, why)) in &found.rules {
        if FILES_ONLY.contains(&rule.as_str()) {
            assert_eq!(*word, "PASS", "{rule}");
            continue;
        }
        let held =
            matches!(why, Some(Reason::NotComplete(Cause::ScopedGaps(s))) if s.ids() == [ID]);
        assert!(*word == "UNKNOWN" && held, "{rule}: {word} {why:?}");
    }
}

#[test]
fn an_undeclared_trojan_horse_holds_each_rule_but_the_rules_of_the_files() {
    let found = run(Vec::new());
    assert_held_by_trojan_horse(&found);
    assert!(found.applied.is_empty() && found.problems.is_empty());
    assert!(found.assumed.is_empty());
}

#[test]
fn a_matched_declaration_decides_each_rule_and_each_pass_names_the_trojan_horse() {
    let found = run(vec![declared("D-EVAL", json!({"line": 7}), &[])]);
    assert_eq!(found.applied, ["D-EVAL"]);
    assert!(found.problems.is_empty());
    for (rule, (word, why)) in &found.rules {
        assert_eq!((*word, why), ("PASS", &None), "{rule}");
        // The rules of the files read nothing that the trojan horse can change: a plain PASS.
        let expected = (!FILES_ONLY.contains(&rule.as_str())).then(|| vec!["D-EVAL".to_owned()]);
        assert_eq!(found.assumed.get(rule).cloned(), expected, "{rule}");
    }
    assert_eq!(found.run, Ok(()));
}

#[test]
fn a_scope_selector_matches_the_module_level() {
    let found = run(vec![declared("D-EVAL", json!({"scope": ""}), &[])]);
    assert_eq!(found.applied, ["D-EVAL"]);
}

#[test]
fn a_declared_load_is_a_real_edge_and_breaks_a_rule_that_forbids_it() {
    let found = run(vec![declared(
        "D-EVAL",
        json!({"line": 7}),
        &["shop.src.data"],
    )]);
    assert_eq!(found.applied, ["D-EVAL"]);
    assert_eq!(word(&found, "DOMAIN-NO-DATA"), "FAIL");
}

#[test]
fn a_declared_change_keeps_the_code_of_the_changed_modules_unknown() {
    let mut item = declared("D-EVAL", json!({"line": 7}), &[]);
    item["changes"] = json!(["shop.src.presentation"]);
    let found = run(vec![item]);
    assert_eq!(found.applied, ["D-EVAL"]);
    let doubts = |rule: &str| match found.rules.get(rule) {
        Some((_, Some(Reason::NotComplete(Cause::ScopedGaps(s))))) => {
            s.doubts().iter().map(|d| d.word()).collect::<Vec<_>>()
        }
        _ => Vec::new(),
    };
    assert_eq!(word(&found, "MODULE-CYCLES"), "UNKNOWN");
    assert_eq!(doubts("MODULE-CYCLES"), [format!("modules: {PAGE}")]);
    // DOMAIN-NO-DATA reads the edges of `domain` only.
    assert_eq!(word(&found, "DOMAIN-NO-DATA"), "PASS");
    assert!(found.assumed.contains_key("DOMAIN-NO-DATA"));
    assert!(found.run.is_err(), "the changed code holds the run");
}

#[test]
fn a_declaration_that_matches_no_trojan_horse_is_a_problem_and_changes_nothing() {
    let stale = [
        (
            declared("D-MOVED", json!({"line": 8}), &[]),
            TrojanHorseProblem::Unmatched(String::new()),
        ),
        (
            declared("D-SCOPE", json!({"scope": "Other.run"}), &[]),
            TrojanHorseProblem::Unmatched(String::new()),
        ),
        (
            {
                let mut item = declared("D-FORM", json!({"line": 7}), &[]);
                item["trojan_horse"] = json!("exec");
                item
            },
            TrojanHorseProblem::Unmatched(String::new()),
        ),
        (
            {
                let mut item = declared("D-WORD", json!({"line": 7}), &[]);
                item["trojan_horse"] = json!("evil");
                item
            },
            TrojanHorseProblem::Form,
        ),
        (
            {
                let mut item = declared("D-OUT", json!({"line": 7}), &[]);
                item["changes"] = json!(["os"]);
                item
            },
            TrojanHorseProblem::ChangesOutside("os".to_owned()),
        ),
        (
            declared("D-NONE", json!({"line": 7}), &["shop.src.nothing"]),
            TrojanHorseProblem::LoadsNothing("shop.src.nothing".to_owned()),
        ),
    ];
    for (item, problem) in stale {
        let id = item["id"].as_str().unwrap_or_default().to_owned();
        let found = run(vec![item]);
        assert_eq!(plain(&found.problems), [(id.clone(), problem)], "{id}");
        assert!(found.applied.is_empty(), "{id}");
        assert_held_by_trojan_horse(&found);
    }
}

#[test]
fn two_declarations_of_one_trojan_horse_apply_neither() {
    let found = run(vec![
        declared("D-ONE", json!({"line": 7}), &[]),
        declared("D-TWO", json!({"scope": ""}), &[]),
    ]);
    assert!(found.applied.is_empty());
    assert_eq!(
        found.problems,
        [
            (
                "D-ONE".to_owned(),
                TrojanHorseProblem::Repeated(vec!["D-TWO".to_owned()])
            ),
            (
                "D-TWO".to_owned(),
                TrojanHorseProblem::Repeated(vec!["D-ONE".to_owned()])
            ),
        ]
    );
    assert_held_by_trojan_horse(&found);
}

#[test]
fn an_outside_load_is_an_external_edge_of_the_trojan_horse_module() {
    // `lodash` is no package of the scan: the trojan horse may import it, so the external rules read it.
    let found = run(vec![declared("D-EVAL", json!({"line": 7}), &["lodash"])]);
    assert_eq!(found.applied, ["D-EVAL"]);
    assert_ne!(word(&found, "EXTERNAL-SHOP"), "UNKNOWN");
    // A load of a member module of DATA-PEERS from `domain` is no sibling edge.
    assert_eq!(word(&found, "DATA-PEERS"), "PASS", "{LOCAL}");
}

#[test]
fn a_declaration_that_matches_two_trojan_horses_applies_to_neither() {
    let two = |reply: &mut Value| {
        let site = json!({"form": "eval", "line": 7, "scope": "Calc.run"});
        let other = json!({"form": "eval", "line": 9, "scope": "Calc.run"});
        trojan_horses(
            reply,
            vec![
                trojan_horse_gap(ID, site),
                trojan_horse_gap("UNKNOWN-0000000000000ddd", other),
            ],
        );
    };
    let found = run_with(
        vec![declared("D-EVAL", json!({"scope": "Calc.run"}), &[])],
        two,
    );
    assert!(found.applied.is_empty());
    assert_eq!(
        found.problems,
        [("D-EVAL".to_owned(), TrojanHorseProblem::Ambiguous(2))]
    );
    let one = |reply: &mut Value| {
        let site = json!({"form": "eval", "line": 7, "scope": "Calc.run"});
        let other = json!({"form": "eval", "line": 9, "scope": "Calc.run"});
        trojan_horses(
            reply,
            vec![
                trojan_horse_gap(ID, site),
                trojan_horse_gap("UNKNOWN-0000000000000ddd", other),
            ],
        );
    };
    let narrowed = declared("D-EVAL", json!({"scope": "Calc.run", "line": 7}), &[]);
    let found = run_with(vec![narrowed], one);
    assert_eq!(found.applied, ["D-EVAL"]);
}

#[test]
fn a_trojan_horse_binding_that_another_module_imports_is_not_applied() {
    // `presentation.page` imports `OrderRepository` from `domain.index`: when the trojan horse site binds
    // that name, the trojan horse runs in `page` too, and no edge of `page` names the reach.
    let bound = |reply: &mut Value| {
        let site = json!({"form": "loader", "line": 1, "binding": "OrderRepository"});
        trojan_horses(reply, vec![trojan_horse_gap(ID, site)]);
    };
    let mut item = declared("D-LOAD", json!({"line": 1}), &[]);
    item["trojan_horse"] = json!("loader");
    let found = run_with(vec![item.clone()], bound);
    assert_eq!(
        found.problems,
        [(
            "D-LOAD".to_owned(),
            TrojanHorseProblem::Exported(vec![PAGE.to_owned()])
        )]
    );
    let free = |reply: &mut Value| {
        let site = json!({"form": "loader", "line": 1, "binding": "load"});
        trojan_horses(reply, vec![trojan_horse_gap(ID, site)]);
    };
    assert_eq!(run_with(vec![item], free).applied, ["D-LOAD"]);
}

/// Two `eval` sites of `Calc.run` at the lines 7 and 9, or `lines`.
fn calc_sites(lines: &'static [u32]) -> impl FnOnce(&mut Value) {
    move |reply: &mut Value| {
        let gaps = lines
            .iter()
            .enumerate()
            .map(|(index, line)| {
                let site = json!({"form": "eval", "line": line, "scope": "Calc.run"});
                trojan_horse_gap(&format!("UNKNOWN-00000000000000e{index}"), site)
            })
            .collect();
        trojan_horses(reply, gaps);
    }
}

#[test]
fn an_edit_above_the_site_moves_the_line_and_a_declaration_with_a_scope_still_applies() {
    // AD-1480: the site is at line 7 of the module level; the hint says 99, as after an edit.
    let found = run(vec![declared(
        "D-EVAL",
        json!({"scope": "", "line": 99}),
        &[],
    )]);
    assert_eq!(found.applied, ["D-EVAL"], "{:?}", found.problems);
    assert!(found.problems.is_empty());
    assert_eq!(word(&found, "DOMAIN-NO-DATA"), "PASS");
    // Without a scope the line must still be exact: the old declaration does not apply.
    let strict = run(vec![declared("D-EVAL", json!({"line": 99}), &[])]);
    assert!(strict.applied.is_empty());
    assert_held_by_trojan_horse(&strict);
}

#[test]
fn a_site_that_moved_to_another_function_is_a_named_gap_that_lists_the_sites() {
    let found = run_with(
        vec![declared(
            "D-EVAL",
            json!({"scope": "Calc.other", "line": 7}),
            &[],
        )],
        calc_sites(&[7]),
    );
    assert!(found.applied.is_empty());
    assert_eq!(
        found.problems,
        [(
            "D-EVAL".to_owned(),
            TrojanHorseProblem::Unmatched("line 7 scope Calc.run".to_owned())
        )]
    );
    assert!(found.run.is_err(), "the site holds the run");
}

#[test]
fn a_scope_that_holds_more_sites_than_declared_needs_the_line_or_the_count() {
    let stale_hint = declared("D-EVAL", json!({"scope": "Calc.run", "line": 50}), &[]);
    let found = run_with(vec![stale_hint.clone()], calc_sites(&[7, 9]));
    assert!(found.applied.is_empty());
    assert_eq!(
        found.problems,
        [("D-EVAL".to_owned(), TrojanHorseProblem::Ambiguous(2))]
    );
    // The line picks one of them.
    let by_line = declared("D-EVAL", json!({"scope": "Calc.run", "line": 9}), &[]);
    assert_eq!(
        run_with(vec![by_line], calc_sites(&[7, 9])).applied,
        ["D-EVAL"]
    );
    // The count says that the declaration holds for both, wherever they are.
    let mut counted = stale_hint;
    counted["count"] = json!(2);
    let found = run_with(vec![counted.clone()], calc_sites(&[7, 9]));
    assert_eq!(found.applied.len(), 2, "{:?}", found.problems);
    // A third site in the scope makes the number differ: the declaration is reviewed again.
    let found = run_with(vec![counted.clone()], calc_sites(&[7, 9, 11]));
    assert!(found.applied.is_empty());
    assert_eq!(
        found.problems,
        [("D-EVAL".to_owned(), TrojanHorseProblem::Ambiguous(3))]
    );
    // A deleted site makes the number smaller: no match, no silent PASS.
    let found = run_with(vec![counted], calc_sites(&[7]));
    assert!(found.applied.is_empty());
    assert!(matches!(
        found.problems.as_slice(),
        [(_, TrojanHorseProblem::Unmatched(_))]
    ));
}
