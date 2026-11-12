// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The scope of an inside-contract tree over the frozen H-typescript reply (AD-385): the proof of
//! each model, the one scope state of the tree, the dynamic imports, the inside `layer_order`
//! rule and the nested mounts.

use archkeel_model::{Cause, Part, Reason, Unsupported};
use serde_json::{json, Value};

use crate::evaluate_tree;
use crate::tree_tests::{
    component, domain, inside, models, not_complete, rows, rule, three, tree, verdict, D, INDEX,
    ORDER, REPO,
};
use crate::Outcome;

#[test]
fn the_proof_of_one_model_never_passes_a_rule_of_another_model() {
    let same = |source: &str| rule("SAME", "complete_assignment", json!({"source": source}));
    let data = inside(
        vec![component("LOCAL", &["shop.src.data"], None)],
        vec![same("shop.src.data")],
    );
    let files = [("a.json", inside(three(), vec![same(D)])), ("b.json", data)];
    let Some(models) = tree(&[("domain", "a.json"), ("data", "b.json")], &files)
        .and_then(|tree| models(&tree, |_| {}))
    else {
        assert_eq!("the tree and its models must load", "loaded");
        return;
    };
    let [first, second] = [&models.mounts()[0], &models.mounts()[1]];
    let foreign: Reason = Part::ForeignRule.into();
    for (model, other) in [(first, second), (second, first), (models.root(), first)] {
        let rule = &other.contract().rules()[0];
        let got = model.scope(|scope| scope.complete(rule).err());
        assert_eq!(got, Some(foreign.clone()));
    }
    let own = &first.contract().rules()[0];
    assert!(first.scope(|scope| scope.complete(own).is_ok()));
    let found = evaluate_tree(&models);
    assert_eq!(verdict(&found, "domain:SAME").0, "PASS");
    assert_eq!(verdict(&found, "data:SAME").0, "PASS");
}

#[test]
fn a_claim_outside_the_parent_holds_back_each_pass_and_keeps_each_fail() {
    let forbid = rule(
        "F",
        "forbidden_dependency",
        json!({"source": REPO, "target": ORDER,
        "include_type_checking": true, "allowed_sources": []}),
    );
    let mut components = three();
    components.push(component("WIDE", &["shop.src.data"], None));
    let found = domain(components, vec![forbid]);
    let cause = not_complete(Cause::InsideSourceDomain("domain".to_owned()));
    assert_eq!(
        verdict(&found, "ASSIGNMENT"),
        ("UNKNOWN".to_owned(), Some(cause))
    );
    assert_eq!(verdict(&found, "domain:F").0, "FAIL");
    assert!(found
        .iter()
        .all(|outcome| verdict(&found, outcome.rule()).0 != "PASS"));
}

#[test]
fn a_rule_of_a_mount_without_subjects_in_its_domain_holds_back_each_pass() {
    let peers = rule(
        "P",
        "sibling_isolation",
        json!({
        "members": ["shop.src.data.local_x2e_ts", "shop.src.data.remote_x2e_ts"],
        "include_type_checking": true}),
    );
    let found = domain(three(), vec![peers]);
    let cause = not_complete(Cause::NoRuleSubjects("domain:P".to_owned()));
    assert_eq!(
        verdict(&found, "ASSIGNMENT"),
        ("UNKNOWN".to_owned(), Some(cause))
    );
}

#[test]
fn a_target_side_of_a_mount_rule_reads_every_module() {
    // The target lies outside the domain: the reference engine reads every module for it.
    let forbid = rule(
        "F",
        "forbidden_dependency",
        json!({"source": D, "target": "shop.src.data",
        "include_type_checking": true, "allowed_sources": []}),
    );
    let found = domain(three(), vec![forbid]);
    assert_eq!(verdict(&found, "domain:F").0, "PASS");
}

/// A gap of the reply between two modules of components that a `requires` entry allows.
fn allowed_pair_gap(reply: &mut Value) {
    let (source, module) = ("shop.src.main_x2e_ts", "shop.src.presentation.page_x2e_ts");
    let gap = json!({
        "id": "UNKNOWN-00000000000000aa", "evidence_class": "UNKNOWN", "area": "source",
        "kind": "collection_gap", "title": "pair", "subjects": [module],
        "evidence_ids": [], "fact_ids": [], "rule_ids": [], "provenance": [],
        "data": {"reason": "pair", "module": module, "source_module": source}
    });
    reply["facts"]["sections"][1]["records"] = json!([gap.clone()]);
    reply["facts"]["coverage"]["gaps"] = json!([gap]);
    reply["facts"]["coverage"]["full_scope"] = json!(false);
}

#[test]
fn a_tree_keeps_every_pair_gap_that_a_root_alone_can_drop() {
    let Some(tree) = tree(
        &[("domain", "a.json")],
        &[("a.json", inside(three(), vec![]))],
    ) else {
        assert_eq!("the tree must load", "loaded");
        return;
    };
    let found = models(&tree, allowed_pair_gap)
        .map(|m| evaluate_tree(&m))
        .unwrap_or_default();
    assert!(held_by_gaps(&found, "ASSIGNMENT", 1));
}

/// True when the rule is UNKNOWN because `count` pair gaps hold it.
fn held_by_gaps(found: &[Outcome], rule: &str, count: usize) -> bool {
    let (word, reason) = verdict(found, rule);
    let held =
        matches!(reason, Some(Reason::NotComplete(Cause::PairGaps(held))) if held.count() == count);
    word == "UNKNOWN" && held
}

/// A gap of the reply from `order` to `index`: both in the domain of the mount `domain`.
fn inner_gap(reply: &mut Value) {
    let (source, module) = (ORDER, INDEX);
    let gap = json!({
        "id": "UNKNOWN-00000000000000ab", "evidence_class": "UNKNOWN", "area": "source",
        "kind": "collection_gap", "title": "pair", "subjects": [module],
        "evidence_ids": [], "fact_ids": [], "rule_ids": [], "provenance": [],
        "data": {"reason": "pair", "module": module, "source_module": source}
    });
    reply["facts"]["sections"][1]["records"] = json!([gap.clone()]);
    reply["facts"]["coverage"]["gaps"] = json!([gap]);
    reply["facts"]["coverage"]["full_scope"] = json!(false);
}

/// Review of #1086 after #1084: a kept gap inside mount A holds the rule of A that reads it, and
/// it does not release the rule of mount B that it cannot change. `drop_allowed_pair_gaps`
/// keeps every gap of a tree and the reference engine holds each rule of the tree, so the gap
/// scope of slice S7 never applies inside a tree (AD-385).
#[test]
fn a_gap_inside_one_mount_holds_its_rule_and_releases_no_rule_of_another_mount() {
    let forbid = rule(
        "F",
        "forbidden_dependency",
        json!({"source": ORDER, "target": INDEX,
        "include_type_checking": true, "allowed_sources": []}),
    );
    let data = inside(
        vec![component("DATA", &["shop.src.data"], None)],
        vec![rule(
            "B",
            "complete_assignment",
            json!({"source": "shop.src.data"}),
        )],
    );
    let files = [("a.json", inside(three(), vec![forbid])), ("b.json", data)];
    let Some(tree) = tree(&[("domain", "a.json"), ("data", "b.json")], &files) else {
        assert_eq!("the tree must load", "loaded");
        return;
    };
    let found = models(&tree, inner_gap)
        .map(|m| evaluate_tree(&m))
        .unwrap_or_default();
    // The gap order -> index can change the reading of `domain:F`.
    assert!(held_by_gaps(&found, "domain:F", 1));
    // `data:B` reads the modules only, which no proven pair changes; still the tree holds it.
    assert!(held_by_gaps(&found, "data:B", 1));
    assert!(held_by_gaps(&found, "ASSIGNMENT", 1));
}

fn dynamic_import(source: &'static str) -> impl FnOnce(&mut Value) {
    move |reply: &mut Value| {
        let limit = json!({
            "id": "UNKNOWN-00000000000000bb", "evidence_class": "UNKNOWN", "area": "source",
            "kind": "dynamic_import_limit", "title": "dynamic", "subjects": [],
            "evidence_ids": [], "fact_ids": [], "rule_ids": [], "provenance": [],
            "data": {"reason": "dynamic", "source_module": source}
        });
        reply["facts"]["sections"][1]["records"] = json!([limit]);
    }
}

#[test]
fn a_dynamic_import_reaches_a_rule_of_a_mount_only_from_its_domain() {
    let complete = rule("C", "complete_external_scope", json!({"source": "shop"}));
    let Some(tree) = tree(
        &[("domain", "a.json")],
        &[("a.json", inside(three(), vec![complete]))],
    ) else {
        assert_eq!("the tree must load", "loaded");
        return;
    };
    let outside = models(&tree, dynamic_import("shop.src.data.local_x2e_ts"))
        .map(|m| evaluate_tree(&m))
        .unwrap_or_default();
    assert_eq!(verdict(&outside, "domain:C").0, "PASS");
    assert_eq!(verdict(&outside, "EXTERNAL-COMPLETE").0, "UNKNOWN");
    let within = models(&tree, dynamic_import(ORDER))
        .map(|m| evaluate_tree(&m))
        .unwrap_or_default();
    let reached = not_complete(Cause::DynamicImport);
    assert_eq!(
        verdict(&within, "domain:C"),
        ("UNKNOWN".to_owned(), Some(reached))
    );
}

#[test]
fn a_profile_limit_of_a_mount_holds_back_each_pass() {
    let boundary = rule("IB", "interface_boundary", json!({}));
    let found = domain(three(), vec![boundary]);
    let part = Reason::Unsupported(Unsupported::ScopeProof(Part::ProfileLimit(
        "domain:IB".into(),
    )));
    assert_eq!(
        verdict(&found, "ASSIGNMENT"),
        ("UNKNOWN".to_owned(), Some(part))
    );
}

#[test]
fn a_layer_order_rule_of_a_mount_is_named_by_its_rows_and_by_its_receipt() {
    // `index` (outer) requires `order` (inner): a row of the reference engine, which cites the
    // inside contract file.
    let layers = rule("LO", "layer_order", json!({"layers": ["outer", "inner"]}));
    let mut components = three();
    for item in &mut components {
        item["layer"] = json!("inner");
    }
    components[2]["layer"] = json!("outer");
    components[2]["requires"] = json!([{"component": "order", "rationale": "r"}]);
    let part = Reason::Unsupported(Unsupported::ScopeProof(Part::MountedLayerOrder));
    let found = domain(components.clone(), vec![layers]);
    assert_eq!(
        verdict(&found, "domain:LO"),
        ("UNKNOWN".to_owned(), Some(part.clone()))
    );
    // Without a row, the receipt of the scope proof names the same part.
    let calm = rule("LO", "layer_order", json!({"layers": ["inner", "outer"]}));
    let file = inside(components, vec![calm]);
    let Some(models) =
        tree(&[("domain", "a.json")], &[("a.json", file)]).and_then(|tree| models(&tree, |_| {}))
    else {
        assert_eq!("the tree and its models must load", "loaded");
        return;
    };
    let mount = &models.mounts()[0];
    let rule = &mount.contract().rules()[0];
    assert_eq!(mount.scope(|scope| scope.complete(rule).err()), Some(part));
}

/// The domain mount with `order` and `rest` (which mounts `rest.json`) and the nested file.
fn nested(rest: &[&str], leaf: Value) -> Vec<Outcome> {
    let middle = inside(
        vec![
            component("ORDER", &[ORDER], None),
            component("REST", rest, Some("rest.json")),
        ],
        vec![],
    );
    tree(
        &[("domain", "a.json")],
        &[("a.json", middle), ("rest.json", leaf)],
    )
    .and_then(|tree| models(&tree, |_| {}))
    .map(|models| evaluate_tree(&models))
    .unwrap_or_default()
}

#[test]
fn a_nested_mount_reads_the_domain_of_its_owner_through_its_clipped_parent() {
    let leaf = inside(
        vec![component("REPO", &[REPO], None)],
        vec![
            rule("A", "complete_assignment", json!({"source": "shop.src"})),
            rule(
                "F",
                "forbidden_dependency",
                json!({"source": INDEX, "target": REPO,
                "include_type_checking": true, "allowed_sources": []}),
            ),
        ],
    );
    let found = nested(&[REPO, INDEX], leaf.clone());
    assert_eq!(rows(&found, "domain:rest:A"), [INDEX]);
    assert_eq!(rows(&found, "domain:rest:F"), ["index -> repository"]);
    // `rest` also claims `shop.src.data`: the clip of `domain` cuts it, so the nested domain
    // holds no module of `data`; the cut claim holds back each PASS.
    let found = nested(&[REPO, INDEX, "shop.src.data"], leaf);
    assert_eq!(rows(&found, "domain:rest:A"), [INDEX]);
    let cause = not_complete(Cause::InsideSourceDomain("domain".to_owned()));
    assert_eq!(
        verdict(&found, "ASSIGNMENT"),
        ("UNKNOWN".to_owned(), Some(cause))
    );
}

#[test]
fn a_nested_mount_reads_the_packages_below_its_clipped_parent() {
    // `rest` claims `shop.src.data` too: the clip of `domain` cuts it, so the packages of `data`
    // are not below the parent of the nested mount, and they are no child of `shop.src` there.
    let leaf = inside(
        vec![component("REPO", &[REPO, INDEX], None)],
        vec![rule(
            "L",
            "root_layout",
            json!({"root": "shop.src", "allowed_children": [D]}),
        )],
    );
    let found = nested(&[REPO, INDEX, "shop.src.data"], leaf);
    assert!(rows(&found, "domain:rest:L").is_empty());
    // The cut claim of `rest` is the reason; a child of `data` would have no record to cite.
    let cause = not_complete(Cause::InsideSourceDomain("domain".to_owned()));
    assert_eq!(
        verdict(&found, "domain:rest:L"),
        ("UNKNOWN".to_owned(), Some(cause))
    );
}

#[test]
fn a_nested_claim_outside_its_parent_names_the_nested_mount() {
    let leaf = inside(
        vec![
            component("REPO", &[REPO], None),
            component("X", &[ORDER], None),
        ],
        vec![],
    );
    let found = nested(&[REPO, INDEX], leaf);
    let cause = not_complete(Cause::InsideSourceDomain("domain:rest".to_owned()));
    assert_eq!(
        verdict(&found, "ASSIGNMENT"),
        ("UNKNOWN".to_owned(), Some(cause))
    );
}

#[test]
fn a_rule_of_a_mount_whose_domain_holds_no_module_has_no_receipt() {
    // `GHOST` owns a package without a module and plans one: the subject check finds the planned
    // module, but no module of the domain gives the receipt (`_observed_rule_modules`).
    let mut ghost = component("GHOST", &["shop.src.domain.ghost"], Some("g.json"));
    ghost["planned"] = json!(["shop.src.domain.ghost.next"]);
    let mut components = three();
    components.push(ghost);
    let mut leaf_component = component("NEXT", &["shop.src.domain.ghost"], None);
    leaf_component["planned"] = json!(["shop.src.domain.ghost.next"]);
    let leaf = inside(
        vec![leaf_component],
        vec![
            rule(
                "E",
                "external_dependency_scope",
                json!({"dependency": "@x/y",
                "allowed_sources": ["shop.src.domain.ghost"]}),
            ),
            rule("C", "complete_external_scope", json!({"source": "shop"})),
            rule("A", "complete_assignment", json!({"source": "shop"})),
        ],
    );
    let files = [("a.json", inside(components, vec![])), ("g.json", leaf)];
    let found = tree(&[("domain", "a.json")], &files)
        .and_then(|tree| models(&tree, |_| {}))
        .map(|models| evaluate_tree(&models))
        .unwrap_or_default();
    assert_eq!(verdict(&found, "ASSIGNMENT").0, "PASS");
    for id in ["domain:ghost:E", "domain:ghost:C", "domain:ghost:A"] {
        assert_eq!(
            verdict(&found, id),
            ("UNKNOWN".to_owned(), Some(Reason::NoSubjects)),
            "{id}"
        );
    }
}

/// Review of #1086, N1: a model of an inside contract without its domain cannot be made. The
/// tree assembly marks each inside contract; `Model::of` and `ModelTree::of` refuse it, also
/// after the clip.
#[test]
fn an_inside_contract_has_a_model_only_through_its_tree() {
    use archkeel_contract::policy::clip_inside;
    use archkeel_model::{Graph, Model, ModelTree};
    let assign = rule("A", "complete_assignment", json!({"source": D}));
    let file = inside(three(), vec![assign]);
    let Some(built) = tree(&[("domain", "a.json")], &[("a.json", file)]) else {
        assert_eq!("the tree does not load", "loaded");
        return;
    };
    let mount = &built.mounts()[0];
    let parent = mount.parent();
    let clipped = clip_inside(parent.packages(), parent.exact_modules(), mount.contract());
    let refused = Reason::Unsupported(Unsupported::InsideRule);
    for contract in [mount.contract(), clipped.contract()] {
        let graph = crate::tests::reply(|_| {})
            .and_then(|reply| Graph::derive(&reply, crate::tests::shop_settings()).ok());
        let Some(graph) = graph else {
            assert_eq!("the reply does not load", "loaded");
            return;
        };
        let found = Model::of(contract, graph).err().map(|refusal| refusal.1);
        assert_eq!(found, Some(refused.clone()));
        let graph = crate::tests::reply(|_| {})
            .and_then(|reply| Graph::derive(&reply, crate::tests::shop_settings()).ok());
        if let Some(graph) = graph {
            let found = ModelTree::of(contract, graph)
                .err()
                .map(|refusal| refusal.1);
            assert_eq!(found, Some(refused.clone()));
        }
    }
    // The root contract of the tree still has its model.
    let graph = crate::tests::reply(|_| {})
        .and_then(|reply| Graph::derive(&reply, crate::tests::shop_settings()).ok());
    assert!(graph.is_some_and(|graph| Model::of(built.root(), graph).is_ok()));
}
