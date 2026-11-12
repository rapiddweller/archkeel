// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The direction kinds of slice S5 (AD-380) over the frozen H-typescript reply.
//!
//! Each test changes the contract or the reply and checks the verdict, the reason and the
//! violations of one rule. Each doubt source of a direction kind has a test where exactly that
//! doubt turns PASS into UNKNOWN.

use archkeel_model::{Cause, Judged, Model, Part, Reason, Settings, Unsupported, Verdict};
use serde_json::{json, Value};

use crate::tests::{contract, reply, shop_settings};
use crate::{evaluate, Outcome, Violation};

/// The contract file of H-typescript as the shell names it.
pub(crate) const CONTRACT_PATH: &str = "architecture-contract.json";

/// The shop settings with the source of the contract after `change`.
pub(crate) fn sourced(change: impl FnOnce(&mut Value)) -> Settings {
    let mut value: Value = serde_json::from_str(
        &std::fs::read_to_string(format!(
            "{}/../../fixtures/H-typescript/architecture-contract.json",
            env!("CARGO_MANIFEST_DIR")
        ))
        .unwrap_or_default(),
    )
    .unwrap_or(Value::Null);
    change(&mut value);
    shop_settings().with_contract_source(CONTRACT_PATH, value.to_string().as_bytes())
}

/// The verdict word, the reason and the violation ids of one rule.
pub(crate) type Seen = (String, Option<Reason>, Vec<String>);

/// The outcome of `rule` after the changes. With `source`, the settings carry the source of
/// the changed contract (its path and bytes).
pub(crate) fn seen(
    rule: &str,
    contract_change: impl FnOnce(&mut Value) + Clone,
    reply_change: impl FnOnce(&mut Value),
    source: bool,
) -> Option<Seen> {
    let settings = if source {
        sourced(contract_change.clone())
    } else {
        shop_settings()
    };
    let contract = contract(contract_change)?;
    let reply = reply(reply_change)?;
    let model = Model::derive(&contract, &reply, settings).ok()?;
    let outcomes = evaluate(&model);
    let outcome = outcomes.iter().find(|o| o.rule() == rule)?;
    Some(word_of(outcome))
}

fn word_of(outcome: &Outcome) -> Seen {
    let ids = outcome.violations().iter().map(describe).collect();
    let Some(decision) = outcome.decision() else {
        return ("DECLARATION".to_owned(), None, ids);
    };
    let word = match decision.verdict() {
        Verdict::Pass(_) => "PASS",
        Verdict::Fail => "FAIL",
        Verdict::Unknown => "UNKNOWN",
    };
    (word.to_owned(), decision.reason().cloned(), ids)
}

fn describe(violation: &Violation) -> String {
    match violation {
        Violation::Forbidden { cited, .. }
        | Violation::Peer { cited, .. }
        | Violation::Unrequired { cited, .. } => {
            format!("{} -> {}", cited.source_module, cited.target_module)
        }
        Violation::OuterLayer(layered) => {
            format!(
                "{} -> {}",
                layered.source_component, layered.target_component
            )
        }
        other => other.id().to_owned(),
    }
}

/// The settings without a contract source.
pub(crate) const PLAIN: bool = false;
/// The settings with the source of the contract.
pub(crate) const SOURCED: bool = true;

pub(crate) fn unchanged(_: &mut Value) {}

/// Point import `index` of `facts.imports` at the module of `file`, and set its type-only flag.
/// The typed target is the local target of that file.
pub(crate) fn point(
    index: usize,
    module: &'static str,
    file: &'static str,
    type_only: bool,
) -> impl FnOnce(&mut Value) + Clone {
    move |value: &mut Value| {
        let id = value["facts"]["imports"][index]["import_id"].clone();
        value["facts"]["imports"][index] = json!({"declaration_file": null, "file": file,
            "import_id": id.clone(), "kind": "local", "module": module, "runtime_file": file});
        let package = module.rsplit_once('.').map_or("", |(head, _)| head);
        for record in records(value).iter_mut().filter(|r| r["id"] == id) {
            record["data"]["target_module"] = json!(module);
            record["data"]["target_package"] = json!(package);
            record["data"]["under_type_checking"] = json!(type_only);
            record["data"]["type_only"] = json!(type_only);
            let source = record["data"]["source_module"].clone();
            let mut subjects = vec![source.as_str().unwrap_or("").to_owned(), module.to_owned()];
            subjects.sort();
            record["subjects"] = json!(subjects);
        }
    }
}

/// The module and the file of `data.local`, `data.remote` and `main`.
pub(crate) const LOCAL: (&str, &str) = ("shop.src.data.local_x2e_ts", "src/data/local.ts");
pub(crate) const REMOTE: (&str, &str) = ("shop.src.data.remote_x2e_ts", "src/data/remote.ts");
pub(crate) const MAIN: (&str, &str) = ("shop.src.main_x2e_ts", "src/main.ts");

/// The import records of the reply.
pub(crate) fn records(value: &mut Value) -> &mut Vec<Value> {
    let index = value["facts"]["sections"]
        .as_array()
        .and_then(|sections| sections.iter().position(|s| s["name"] == "imports"))
        .unwrap_or(0);
    let section = &mut value["facts"]["sections"][index]["records"];
    if !section.is_array() {
        *section = json!([]);
    }
    section.as_array_mut().unwrap()
}

/// The imports of `facts.imports` by index (H-typescript): 0 `data.local -> domain.repository`,
/// 1 `data.remote -> domain.repository`, 2 `domain.index -> domain.order`, 3 `domain.index ->
/// domain.repository` (a type-only re-export), 7 `presentation.page -> domain.index`.
pub(crate) const PAGE_IMPORT: usize = 7;

pub(crate) fn rule(contract: &mut Value, id: &str) -> Option<usize> {
    contract["rules"]
        .as_array()?
        .iter()
        .position(|rule| rule["id"] == id)
}

pub(crate) fn set_rule(
    id: &'static str,
    field: &'static str,
    value: Value,
) -> impl FnOnce(&mut Value) + Clone {
    move |contract: &mut Value| {
        if let Some(index) = rule(contract, id) {
            contract["rules"][index][field] = value;
        }
    }
}

pub(crate) fn both(
    first: impl FnOnce(&mut Value) + Clone,
    second: impl FnOnce(&mut Value) + Clone,
) -> impl FnOnce(&mut Value) + Clone {
    move |value: &mut Value| {
        first(value);
        second(value);
    }
}

pub(crate) fn not_complete(cause: Cause) -> Option<Reason> {
    Some(Reason::NotComplete(cause))
}

pub(crate) fn unread(part: Part) -> Option<Reason> {
    Some(Reason::Unsupported(Unsupported::ScopeProof(part)))
}

fn pass() -> Seen {
    ("PASS".to_owned(), None, Vec::new())
}

#[test]
fn a_clean_run_passes_the_forbidden_and_the_sibling_rule() {
    for id in ["DOMAIN-NO-DATA", "DATA-PEERS"] {
        assert_eq!(seen(id, unchanged, unchanged, PLAIN), Some(pass()), "{id}");
    }
}

#[test]
fn a_forbidden_import_fails_also_when_it_is_a_type_only_re_export() {
    // Import 3 is a type-only re-export of `domain.index`; import 2 is a value import.
    let reply = both(
        point(3, LOCAL.0, LOCAL.1, true),
        point(2, LOCAL.0, LOCAL.1, false),
    );
    let found = seen("DOMAIN-NO-DATA", unchanged, reply.clone(), PLAIN);
    let edge = "shop.src.domain.index_x2e_ts -> shop.src.data.local_x2e_ts".to_owned();
    assert_eq!(
        found,
        Some(("FAIL".to_owned(), None, vec![edge.clone(), edge.clone()]))
    );
    // Without type-only imports the rule sees the value import only.
    let value_only = set_rule("DOMAIN-NO-DATA", "include_type_checking", json!(false));
    let found = seen("DOMAIN-NO-DATA", value_only, reply, PLAIN);
    assert_eq!(found, Some(("FAIL".to_owned(), None, vec![edge])));
}

#[test]
fn a_rule_that_leaves_out_type_only_imports_passes_a_type_only_import() {
    let value_only = set_rule("DOMAIN-NO-DATA", "include_type_checking", json!(false));
    let reply = point(3, LOCAL.0, LOCAL.1, true);
    assert_eq!(
        seen("DOMAIN-NO-DATA", value_only, reply, PLAIN),
        Some(pass())
    );
}

#[test]
fn an_allowed_source_is_an_exact_module_not_a_prefix() {
    let reply = point(2, LOCAL.0, LOCAL.1, false);
    let exact = set_rule(
        "DOMAIN-NO-DATA",
        "allowed_sources",
        json!(["shop.src.domain.index_x2e_ts"]),
    );
    assert_eq!(
        seen("DOMAIN-NO-DATA", exact, reply.clone(), PLAIN),
        Some(pass())
    );
    let prefix = set_rule(
        "DOMAIN-NO-DATA",
        "allowed_sources",
        json!(["shop.src.domain"]),
    );
    let found = seen("DOMAIN-NO-DATA", prefix, reply, PLAIN).map(|s| s.0);
    assert_eq!(found.as_deref(), Some("FAIL"));
}

#[test]
fn a_whole_package_ban_selects_the_exact_modules_of_the_target_component() {
    // `data` also claims `shop.src.main_x2e_ts` exactly; `presentation.page` imports it.
    let claim = |c: &mut Value| {
        if let Some(index) = c["components"]
            .as_array()
            .and_then(|all| all.iter().position(|x| x["label"] == "data"))
        {
            c["components"][index]["exact_modules"] = json!(["shop.src.main_x2e_ts"]);
        }
        if let Some(rules) = c["rules"].as_array_mut() {
            rules.push(json!({"id": "PAGE-NO-DATA", "kind": "forbidden_dependency",
                "rationale": "r", "provenance": ["p"], "decided_by": "architect",
                "source": "shop.src.presentation", "target": "shop.src.data",
                "include_type_checking": true, "allowed_sources": []}));
        }
    };
    let page = point(PAGE_IMPORT, MAIN.0, MAIN.1, false);
    let found = seen("PAGE-NO-DATA", claim, page.clone(), PLAIN).map(|s| (s.0, s.2));
    let edge = "shop.src.presentation.page_x2e_ts -> shop.src.main_x2e_ts".to_owned();
    assert_eq!(found, Some(("FAIL".to_owned(), vec![edge])));
    // An exact target selects only its own name: the pair is not the whole component.
    let exact = both(
        claim,
        set_rule("PAGE-NO-DATA", "target_match", json!("exact")),
    );
    let found = seen("PAGE-NO-DATA", exact, page, PLAIN).map(|s| s.0);
    assert_ne!(found.as_deref(), Some("FAIL"));
}

#[test]
fn a_symbol_rule_leaves_an_import_with_unknown_names_undecided() {
    // `presentation.page` imports `domain.index` (type-only, names unknown): the rule cannot
    // tell whether it uses `Order`.
    let symbol = |c: &mut Value| {
        if let Some(rules) = c["rules"].as_array_mut() {
            rules.push(json!({"id": "SYMBOL", "kind": "forbidden_dependency",
                "rationale": "r", "provenance": ["p"], "decided_by": "architect",
                "source": "shop.src.presentation", "target": "shop.src.domain",
                "target_symbol": "Order", "include_type_checking": true, "allowed_sources": []}));
        }
    };
    let found = seen("SYMBOL", symbol, unchanged, PLAIN);
    assert_eq!(
        found,
        Some((
            "UNKNOWN".to_owned(),
            not_complete(Cause::Undecided(1)),
            Vec::new()
        ))
    );
    // The same rule leaves type-only imports out: no position is undecided, and the profile
    // limit of a symbol selector names the part that the core cannot read.
    let value_only = both(
        symbol,
        set_rule("SYMBOL", "include_type_checking", json!(false)),
    );
    let found = seen("SYMBOL", value_only, unchanged, PLAIN).map(|s| s.1);
    assert_eq!(found, Some(unread(Part::ProfileLimit("SYMBOL".to_owned()))));
}

#[test]
fn the_matcher_judges_a_named_symbol_as_fail_and_another_known_name_as_pass() {
    let symbol = |target: &'static str| {
        move |c: &mut Value| {
            if let Some(rules) = c["rules"].as_array_mut() {
                rules.push(json!({"id": "SYMBOL", "kind": "forbidden_dependency",
                    "rationale": "r", "provenance": ["p"], "decided_by": "architect",
                    "source": "shop.src", "target": "shop.src.data",
                    "target_symbol": target, "include_type_checking": true,
                    "allowed_sources": []}));
            }
        }
    };
    // `main` imports `data.local` by the known name `local`.
    for (target, expected) in [("local", Judged::Fail), ("other", Judged::Pass)] {
        let (Some(own), Some(reply)) = (contract(symbol(target)), reply(unchanged)) else {
            return assert_eq!("the inputs load", "");
        };
        let Ok(model) = Model::derive(&own, &reply, shop_settings()) else {
            return assert_eq!("the model derives", "");
        };
        let Some(archkeel_contract::Rule::ForbiddenDependency(rule)) = own.rules().last() else {
            return assert_eq!("the rule loads", "");
        };
        let judged: Vec<Judged> = archkeel_model::forbidden(&model, rule)
            .into_iter()
            .map(|(_, j)| j)
            .collect();
        assert_eq!(judged, vec![expected], "{target}");
    }
}

#[test]
fn a_peer_import_fails_the_sibling_rule_and_a_type_only_peer_does_not() {
    // Import 0 is `data.local -> domain.repository`; point it at `data.remote`.
    let peer = point(0, REMOTE.0, REMOTE.1, true);
    let found = seen("DATA-PEERS", unchanged, peer.clone(), PLAIN);
    let edge = "shop.src.data.local_x2e_ts -> shop.src.data.remote_x2e_ts".to_owned();
    assert_eq!(found, Some(("FAIL".to_owned(), None, vec![edge])));
    // A rule that leaves out type-only imports does not see it.
    let value_only = set_rule("DATA-PEERS", "include_type_checking", json!(false));
    assert_eq!(seen("DATA-PEERS", value_only, peer, PLAIN), Some(pass()));
}

#[test]
fn a_self_edge_inside_one_member_is_no_peer_import() {
    // `data.* -> domain.repository` crosses two members; `domain.index -> domain.order` and
    // `domain.repository -> domain.order` stay inside one member.
    let members = set_rule(
        "DATA-PEERS",
        "members",
        json!(["shop.src.data", "shop.src.domain"]),
    );
    let mut found = seen("DATA-PEERS", members, unchanged, PLAIN)
        .map(|s| s.2)
        .unwrap_or_default();
    found.sort();
    let expected = vec![
        "shop.src.data.local_x2e_ts -> shop.src.domain.repository_x2e_ts".to_owned(),
        "shop.src.data.remote_x2e_ts -> shop.src.domain.repository_x2e_ts".to_owned(),
    ];
    assert_eq!(found, expected);
}

#[test]
fn an_allowed_dependency_is_a_declaration_without_a_verdict() {
    let allow = |c: &mut Value| {
        if let Some(rules) = c["rules"].as_array_mut() {
            rules.push(json!({"id": "ALLOW", "kind": "allowed_dependency",
                "rationale": "r", "provenance": ["p"], "decided_by": "architect",
                "source": "shop.src.main_x2e_ts", "target": "shop.src.data"}));
        }
    };
    let found = seen("ALLOW", allow, unchanged, PLAIN);
    assert_eq!(found, Some(("DECLARATION".to_owned(), None, Vec::new())));
}
