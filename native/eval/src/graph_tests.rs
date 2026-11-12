// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The graph of the model that slice S7 reads (AD-374): the order of `Graph::cycles`.

use archkeel_model::Model;
use serde_json::{json, Value};

use crate::tests::{contract, reply_or_refusal, shop_settings};

/// Point the import record at `index` to `target` (module, package, file).
fn redirect(value: &mut Value, index: usize, target: [&str; 3]) {
    let Some(sections) = value["facts"]["sections"].as_array_mut() else {
        return;
    };
    let Some(imports) = sections
        .iter_mut()
        .find(|section| section["name"] == "imports")
    else {
        return;
    };
    let record = &mut imports["records"][index];
    record["data"]["target_module"] = json!(target[0]);
    record["data"]["target_package"] = json!(target[1]);
    let id = record["id"].clone();
    if let Some(targets) = value["facts"]["imports"].as_array_mut() {
        for typed in targets.iter_mut().filter(|typed| typed["import_id"] == id) {
            typed["module"] = json!(target[0]);
            typed["file"] = json!(target[2]);
            typed["runtime_file"] = json!(target[2]);
        }
    }
}

#[test]
fn the_cycles_of_the_graph_are_sorted_by_id() {
    // index -> page closes index <-> page, and local -> main closes main <-> local: two module
    // cycles and the package cycles of their packages.
    let reply = reply_or_refusal(|value| {
        let page = [
            "shop.src.presentation.page_x2e_ts",
            "shop.src.presentation",
            "src/presentation/page.ts",
        ];
        redirect(value, 0, page);
        redirect(
            value,
            2,
            ["shop.src.main_x2e_ts", "shop.src", "src/main.ts"],
        );
    });
    let reply = reply.unwrap();
    let contract = contract(|_| {}).unwrap();
    let model = Model::derive(&contract, &reply, shop_settings()).unwrap();
    let ids: Vec<&str> = model
        .graph()
        .cycles()
        .iter()
        .map(|cycle| cycle.id())
        .collect();
    assert_eq!(ids.len(), 4, "{ids:?}");
    let mut sorted = ids.clone();
    sorted.sort_unstable();
    assert_eq!(ids, sorted);
}
