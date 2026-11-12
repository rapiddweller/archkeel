// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The edges across the border of a mount (AD-385, review of #1086 S1). A rule of a mount reads
//! each import whose source lies in its domain, whatever the domain of the target: an edge that
//! leaves the mount, or that enters another mount, is a violation of the rule of its source. An
//! edge that enters the mount from outside is not.

use archkeel_model::{Graph, ModelTree};
use serde_json::{json, Value};

use crate::tests::{reply, shop_settings};
use crate::tree_tests::{component, inside, rows, rule, three, tree, verdict, D};
use crate::{evaluate_tree, Outcome};

const LOCAL: &str = "shop.src.data.local_x2e_ts";
const REMOTE: &str = "shop.src.data.remote_x2e_ts";

/// The reply with the import `repository -> order` turned into `repository -> data.local`: an
/// edge from the domain of `domain` to the domain of `data`.
fn leak(value: &mut Value) {
    let imports = value["facts"]["imports"]
        .as_array()
        .cloned()
        .unwrap_or_default();
    let index = imports
        .iter()
        .position(|item| item["import_id"] == "IMP_BINDING-be673441fde62c78");
    assert!(index.is_some(), "the import repository -> order");
    let target = json!({"kind": "local", "module": LOCAL, "file": "src/data/local.ts",
        "runtime_file": "src/data/local.ts", "declaration_file": null});
    if let Some(index) = index {
        crate::external_tests::retarget(value, index, LOCAL, "shop.src.data", target);
    }
}

fn forbid(id: &str, source: &str, target: &str) -> Value {
    rule(
        id,
        "forbidden_dependency",
        json!({"source": source, "target": target,
        "include_type_checking": true, "allowed_sources": []}),
    )
}

/// The outcomes of the tree with each `(label, path)` mounted, over the leaking reply.
fn leaking(mounts: &[(&str, &str)], files: &[(&str, Value)]) -> Vec<Outcome> {
    let graph = reply(leak).and_then(|reply| Graph::derive(&reply, shop_settings()).ok());
    let models = tree(mounts, files)
        .zip(graph)
        .and_then(|(tree, graph)| ModelTree::tree(&tree, graph).ok());
    assert!(models.is_some(), "the tree and its models load");
    models.map(|m| evaluate_tree(&m)).unwrap_or_default()
}

#[test]
fn an_edge_that_leaves_the_mount_fails_the_rule_of_the_mount() {
    let file = inside(three(), vec![forbid("OUT", D, "shop.src.data")]);
    let found = leaking(&[("domain", "a.json")], &[("a.json", file)]);
    assert_eq!(rows(&found, "domain:OUT"), ["repository -> local"]);
    assert_eq!(verdict(&found, "domain:OUT").0, "FAIL");
}

#[test]
fn an_edge_between_two_mounts_fails_only_the_rule_of_its_source() {
    let data = inside(
        vec![
            component("LOCAL", &[LOCAL], None),
            component("REMOTE", &[REMOTE], None),
        ],
        vec![
            forbid("IN", "shop.src.data", D),
            // The leaking edge enters `data` from `domain`: no violation of a rule of `data`.
            forbid("ENTER", "shop.src", LOCAL),
        ],
    );
    let files = [
        (
            "a.json",
            inside(three(), vec![forbid("OUT", D, "shop.src.data")]),
        ),
        ("b.json", data),
    ];
    let found = leaking(&[("domain", "a.json"), ("data", "b.json")], &files);
    assert_eq!(rows(&found, "domain:OUT"), ["repository -> local"]);
    let mut entering = rows(&found, "data:IN");
    entering.sort();
    assert_eq!(entering, ["local -> repository", "remote -> repository"]);
    assert_eq!(verdict(&found, "data:ENTER").0, "PASS");
}
