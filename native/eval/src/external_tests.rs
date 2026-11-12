// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The external rule kinds of S2 over the frozen H-typescript reply with retargeted imports.

use archkeel_model::{Decision, Incomplete, Model, Reason, Refusal, Settings, Verdict};
use serde_json::{json, Value};

use crate::tests::{contract, reply, shop_profile, shop_settings};
use crate::{evaluate, Outcome, Violation};

/// The import of `shop.src.domain.index_x2e_ts` that is the first record of the imports section.
const DOMAIN: usize = 3;

/// Point import `index` of the reply at a typed target; the record agrees with it.
fn retarget(value: &mut Value, index: usize, module: &str, package: &str, target: Value) {
    let id = value["facts"]["imports"][index]["import_id"].clone();
    let mut typed = target;
    typed["import_id"] = id.clone();
    value["facts"]["imports"][index] = typed;
    let Some(sections) = value["facts"]["sections"].as_array_mut() else {
        return;
    };
    for section in sections.iter_mut().filter(|s| s["name"] == "imports") {
        let Some(records) = section["records"].as_array_mut() else {
            continue;
        };
        for record in records.iter_mut().filter(|r| r["id"] == id) {
            record["data"]["target_module"] = json!(module);
            record["data"]["target_package"] = json!(package);
            let source = record["data"]["source_module"]
                .as_str()
                .unwrap_or("")
                .to_owned();
            let mut subjects = vec![source, module.to_owned()];
            subjects.sort();
            record["subjects"] = json!(subjects);
        }
    }
}

fn external(index: usize, package: &str) -> impl FnOnce(&mut Value) + '_ {
    move |value| {
        let target = json!({"kind": "external", "package": package});
        // The module name is not below the package name: only the package can match.
        retarget(value, index, "vendor.entry", package, target);
    }
}

/// The outcomes of the two external rules after the changes.
fn run(
    contract_change: impl FnOnce(&mut Value),
    reply_change: impl FnOnce(&mut Value),
    settings: Settings,
) -> Vec<Outcome> {
    let (Some(contract), Some(reply)) = (contract(contract_change), reply(reply_change)) else {
        return Vec::new();
    };
    let Ok(model) = Model::derive(&contract, &reply, settings) else {
        return Vec::new();
    };
    evaluate(&contract, &model)
        .into_iter()
        .filter(|outcome| outcome.rule().starts_with("EXTERNAL-"))
        .collect()
}

fn of<'a>(outcomes: &'a [Outcome], rule: &str) -> Vec<&'a Violation> {
    outcomes
        .iter()
        .filter(|outcome| outcome.rule() == rule)
        .flat_map(Outcome::violations)
        .collect()
}

fn decision<'a>(outcomes: &'a [Outcome], rule: &str) -> Option<&'a Decision> {
    outcomes
        .iter()
        .find(|o| o.rule() == rule)
        .and_then(Outcome::decision)
}

fn dependencies(violations: &[&Violation]) -> Vec<String> {
    violations
        .iter()
        .filter_map(|violation| match violation {
            Violation::OutsideScope { cited, .. } => Some(cited.source_module.clone()),
            Violation::Undeclared { dependency, .. } => Some(dependency.clone()),
            _ => None,
        })
        .collect()
}

#[test]
fn the_clean_reply_has_no_external_violation_and_passes_with_the_scope_proof() {
    let outcomes = run(|_| {}, |_| {}, shop_settings());
    assert_eq!(outcomes.len(), 2);
    // Each local import has an internal root, so no import is external.
    assert!(outcomes.iter().all(|o| o.violations().is_empty()));
    assert!(outcomes
        .iter()
        .all(|o| matches!(o.decision().unwrap().verdict(), Verdict::Pass(_))));
}

#[test]
fn an_external_package_matches_by_its_name_and_a_declared_one_is_complete() {
    let outcomes = run(|_| {}, external(DOMAIN, "@shop/transport"), shop_settings());
    assert_eq!(of(&outcomes, "EXTERNAL-SHOP").len(), 1);
    assert_eq!(
        decision(&outcomes, "EXTERNAL-SHOP"),
        Some(&Decision::fail())
    );
    assert!(of(&outcomes, "EXTERNAL-COMPLETE").is_empty());
}

#[test]
fn an_undeclared_dotted_package_is_one_dependency() {
    let outcomes = run(
        |_| {},
        external(DOMAIN, "transport.client"),
        shop_settings(),
    );
    let found = of(&outcomes, "EXTERNAL-COMPLETE");
    assert_eq!(dependencies(&found), vec!["transport.client".to_owned()]);
    assert!(of(&outcomes, "EXTERNAL-SHOP").is_empty());
}

#[test]
fn a_builtin_import_matches_by_its_module_and_is_never_undeclared() {
    let builtin = |value: &mut Value| {
        retarget(
            value,
            DOMAIN,
            "fs",
            "fs",
            json!({"kind": "builtin", "name": "fs"}),
        );
    };
    let refusal = crate::tests::reply_or_refusal(builtin).err();
    assert_eq!(refusal, None);
    let outcomes = run(|_| {}, builtin, shop_settings());
    assert_eq!(outcomes.len(), 2);
    assert!(of(&outcomes, "EXTERNAL-COMPLETE").is_empty());
    let scoped = |value: &mut Value| {
        if let Some(rules) = value["rules"].as_array_mut() {
            for rule in rules.iter_mut().filter(|r| r["id"] == "EXTERNAL-SHOP") {
                rule["dependency"] = json!("fs");
            }
        }
    };
    let outcomes = run(scoped, builtin, shop_settings());
    assert_eq!(outcomes.len(), 2);
    assert_eq!(of(&outcomes, "EXTERNAL-SHOP").len(), 1);
}

#[test]
fn the_standard_library_of_the_shell_settings_is_exempt() {
    let std_settings = Settings::new(
        "shop".to_owned(),
        shop_profile(),
        vec!["platform".to_owned()],
    );
    let outcomes = run(|_| {}, external(DOMAIN, "platform"), std_settings);
    assert!(of(&outcomes, "EXTERNAL-COMPLETE").is_empty());
    let outcomes = run(|_| {}, external(DOMAIN, "platform"), shop_settings());
    assert_eq!(
        dependencies(&of(&outcomes, "EXTERNAL-COMPLETE")),
        vec!["platform"]
    );
}

#[test]
fn a_relative_import_is_never_undeclared() {
    let relative = |value: &mut Value| {
        external(DOMAIN, "transport-client")(value);
        if let Some(sections) = value["facts"]["sections"].as_array_mut() {
            for section in sections.iter_mut().filter(|s| s["name"] == "imports") {
                section["records"][0]["data"]["relative_level"] = json!(1);
            }
        }
    };
    let outcomes = run(|_| {}, relative, shop_settings());
    assert_eq!(outcomes.len(), 2, "the store accepts the relative import");
    assert!(of(&outcomes, "EXTERNAL-COMPLETE").is_empty());
}

#[test]
fn an_exact_source_allows_only_the_module_of_its_name() {
    let exact = |value: &mut Value| {
        if let Some(rules) = value["rules"].as_array_mut() {
            for rule in rules.iter_mut().filter(|r| r["id"] == "EXTERNAL-SHOP") {
                rule["dependency"] = json!("shop.src.domain");
                rule["allowed_sources"] = json!([]);
                rule["exact_sources"] = json!(["shop.src.data", "shop.src.data.local_x2e_ts"]);
            }
        }
    };
    let outcomes = run(exact, |_| {}, shop_settings());
    let sources = dependencies(&of(&outcomes, "EXTERNAL-SHOP"));
    assert!(
        sources.contains(&"shop.src.data.remote_x2e_ts".to_owned()),
        "{sources:?}"
    );
    assert!(
        !sources.contains(&"shop.src.data.local_x2e_ts".to_owned()),
        "{sources:?}"
    );
}

#[test]
fn an_unresolved_import_gives_unknown_and_a_violation_still_fails() {
    let unresolved = |index: usize| {
        move |value: &mut Value| {
            let target = json!({"kind": "unresolved", "specifier": "./gone",
                                "reason": "Unresolved module: ./gone"});
            retarget(value, index, "./gone", "shop.src", target);
        }
    };
    let outcomes = run(|_| {}, unresolved(1), shop_settings());
    let unknown = Decision::unknown(Reason::Incomplete(Incomplete::UnknownImports(1)));
    assert_eq!(decision(&outcomes, "EXTERNAL-SHOP"), Some(&unknown));
    assert_eq!(decision(&outcomes, "EXTERNAL-COMPLETE"), Some(&unknown));
    let both = |value: &mut Value| {
        unresolved(1)(value);
        external(DOMAIN, "@shop/transport")(value);
    };
    let outcomes = run(|_| {}, both, shop_settings());
    assert_eq!(
        decision(&outcomes, "EXTERNAL-SHOP"),
        Some(&Decision::fail())
    );
    assert_eq!(decision(&outcomes, "EXTERNAL-COMPLETE"), Some(&unknown));
}

#[test]
fn complete_external_scope_checks_only_the_imports_below_its_source() {
    let narrow = |value: &mut Value| {
        if let Some(rules) = value["rules"].as_array_mut() {
            for rule in rules.iter_mut().filter(|r| r["id"] == "EXTERNAL-COMPLETE") {
                rule["source"] = json!("shop.src.data");
            }
        }
    };
    let outcomes = run(
        narrow,
        external(DOMAIN, "transport-client"),
        shop_settings(),
    );
    assert_eq!(outcomes.len(), 2);
    assert!(of(&outcomes, "EXTERNAL-COMPLETE").is_empty());
    // Import 1 is of `shop.src.data.remote_x2e_ts`, below the source.
    let outcomes = run(narrow, external(1, "transport-client"), shop_settings());
    assert_eq!(
        dependencies(&of(&outcomes, "EXTERNAL-COMPLETE")),
        vec!["transport-client"]
    );
}

#[test]
fn an_allowed_source_matches_whole_segments_only() {
    // `shop.src.dat` is a text prefix of `shop.src.data.*`, not a scope of it.
    let partial = |value: &mut Value| {
        if let Some(rules) = value["rules"].as_array_mut() {
            for rule in rules.iter_mut().filter(|r| r["id"] == "EXTERNAL-SHOP") {
                rule["dependency"] = json!("shop.src.domain");
                rule["allowed_sources"] = json!(["shop.src.dat"]);
            }
        }
    };
    let outcomes = run(partial, |_| {}, shop_settings());
    let sources = dependencies(&of(&outcomes, "EXTERNAL-SHOP"));
    assert!(
        sources.contains(&"shop.src.data.local_x2e_ts".to_owned()),
        "{sources:?}"
    );
}

#[test]
fn settings_that_do_not_hold_for_the_reply_give_no_model() {
    let (Some(contract), Some(reply)) = (contract(|_| {}), reply(|_| {})) else {
        return assert_eq!("the golden inputs", "");
    };
    let derive = |settings: Settings| Model::derive(&contract, &reply, settings).err();
    assert_eq!(derive(shop_settings()), None);
    let other = Settings::new("shop".to_owned(), "other".to_owned(), Vec::new());
    assert_eq!(
        derive(other),
        Some(Reason::Refused(Refusal::ProfileMismatch))
    );
    for namespace in ["", "nothing", "sho"] {
        let settings = Settings::new(namespace.to_owned(), shop_profile(), Vec::new());
        assert!(matches!(
            derive(settings),
            Some(Reason::Refused(Refusal::OutsideNamespace(_)))
        ));
    }
}
