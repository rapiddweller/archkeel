// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: `type_reach_model.rs`. Each test builds a tiny facts file by hand: one change of one fact
// moves one pair from excluded to kept. The runs with the real compiler are in `tests/rust_reach_fixtures`.

use super::{Cause, Mode, Reach, Verdict};
use crate::type_reach_facts::Facts;
use crate::type_reach_filter::Filter;
use serde_json::{json, Value};
use std::collections::{BTreeMap, BTreeSet};

/// A facts file: texts in the records become ids of a string table, as the driver writes them.
fn file(records: &[Value], crate_types: &[&str]) -> String {
    let mut names: Vec<String> = Vec::new();
    let mut id = |text: &str| -> Value {
        let at = names.iter().position(|n| n == text).unwrap_or_else(|| {
            names.push(text.to_string());
            names.len() - 1
        });
        json!(at)
    };
    let mut lines = vec![String::new(), String::new()];
    for record in records {
        let mut record = record.clone();
        for (key, field) in record.as_object_mut().unwrap() {
            if key == "k" || key == "line" || key == "run" {
                continue;
            }
            match field {
                Value::String(text) => *field = id(text),
                Value::Array(all) => all.iter_mut().for_each(|v| *v = id(v.as_str().unwrap())),
                _ => {}
            }
        }
        lines.push(record.to_string());
    }
    lines[0] = json!({"k": "build", "crate_types": crate_types}).to_string();
    lines[1] = json!({"k": "str", "v": names}).to_string();
    lines.join("\n")
}

pub(super) fn facts(records: &[Value]) -> Facts {
    facts_of(&[(records, &[])])
}

/// The facts of several files, each with the crate types of its build record.
pub(super) fn facts_of(files: &[(&[Value], &[&str])]) -> Facts {
    let mut facts = Facts::empty();
    for (records, types) in files {
        facts.absorb(&file(records, types)).unwrap();
    }
    facts
}

pub(super) fn module(m: &str, mentions: &[&str], dyns: &[&str], opaques: &[&str]) -> Value {
    json!({"k": "mod", "m": m, "file": "f", "mentions": mentions, "dyn": dyns, "opaque": opaques, "dyn_in": []})
}

pub(super) fn imp(module: &str, tr: Option<&str>, adts: &[&str], assoc: &[&str]) -> Value {
    json!({"k": "impl", "m": module, "trait": tr, "self_adts": adts, "assoc": assoc, "items": [], "run": true, "line": 1})
}

pub(super) fn known() -> BTreeSet<String> {
    ["a", "b", "c"]
        .iter()
        .map(|m| format!("native.k.{m}"))
        .collect()
}

pub(super) fn verdict(facts: &Facts, mode: &Mode) -> &'static str {
    let reach = Reach::new(facts, &known());
    match reach.decide(("native.k.a", "native.k.b"), mode, &mut BTreeMap::new()) {
        Verdict::Excluded => "excluded",
        Verdict::Kept(Cause::Reached) => "kept",
        Verdict::Kept(Cause::NoFacts) => "no facts",
        Verdict::Kept(Cause::NoImpl) => "no impl",
        Verdict::Kept(Cause::NonAdtSelf) => "non-adt self",
    }
}

pub(super) fn target() -> Value {
    imp("k::b", None, &["k::b::X"], &[])
}

#[test]
fn a_mention_and_a_field_keep_the_pair_and_no_way_to_hold_the_type_excludes_it() {
    let direct = facts(&[module("k::a", &["k::b::X"], &[], &[]), target()]);
    assert_eq!(verdict(&direct, &Mode::Rta), "kept");
    let control = facts(&[module("k::a", &["k::a::Y"], &[], &[]), target()]);
    assert_eq!(verdict(&control, &Mode::Rta), "excluded");
    let field = json!({"k": "adt", "d": "k::a::W", "m": "k::a", "file": "f", "fields": ["k::b::X"], "dyn": []});
    let inside = facts(&[module("k::a", &["k::a::W"], &[], &[]), field, target()]);
    assert_eq!(verdict(&inside, &Mode::Rta), "kept");
}

#[test]
fn the_other_causes_keep_the_pair() {
    assert_eq!(verdict(&facts(&[target()]), &Mode::Rta), "no facts");
    assert_eq!(
        verdict(&facts(&[module("k::a", &[], &[], &[])]), &Mode::Rta),
        "no impl"
    );
    let blanket = imp("k::b", Some("k::Tr"), &[], &[]);
    assert_eq!(
        verdict(
            &facts(&[module("k::a", &[], &[], &[]), blanket]),
            &Mode::Rta
        ),
        "non-adt self"
    );
    let no_code = json!({"k": "impl", "m": "k::b", "trait": null, "self_adts": ["k::b::X"], "assoc": [], "items": [], "run": false, "line": 1});
    assert_eq!(
        verdict(
            &facts(&[module("k::a", &["k::b::X"], &[], &[]), no_code]),
            &Mode::Rta
        ),
        "no impl"
    );
}

#[test]
fn an_inline_module_joins_its_file_and_the_longest_known_module_wins() {
    let inline = imp("k::b::tests", None, &["k::b::X"], &[]);
    assert_eq!(
        verdict(
            &facts(&[module("k::a::inner", &["k::b::X"], &[], &[]), inline]),
            &Mode::Rta
        ),
        "kept"
    );
}

#[test]
fn a_reached_dyn_trait_adds_what_is_coerced_to_it_and_loose_adds_every_mentioned_type() {
    let coerced =
        json!({"k": "coerce", "tr": "k::Tr", "src": ["k::b::X"], "src_dyn": [], "param_in": []});
    let other =
        json!({"k": "coerce", "tr": "k::Tr", "src": ["k::c::Z"], "src_dyn": [], "param_in": []});
    let holds_dyn = module("k::a", &[], &["k::Tr"], &[]);
    let elsewhere = module("k::c", &["k::b::X"], &[], &[]);
    assert_eq!(
        verdict(&facts(&[holds_dyn.clone(), coerced, target()]), &Mode::Rta),
        "kept"
    );
    let control = facts(&[holds_dyn, other, elsewhere, target()]);
    assert_eq!(verdict(&control, &Mode::Rta), "excluded");
    assert_eq!(verdict(&control, &Mode::Loose), "kept");
}

#[test]
fn a_cast_from_a_type_parameter_takes_the_instances_of_its_function_h1() {
    let cast = json!({"k": "coerce", "tr": "k::Tr", "src": [], "src_dyn": [], "param_in": ["k::c::register"]});
    let function = json!({"k": "fn", "f": "k::c::register", "m": "k::c", "implements": null});
    let call = json!({"k": "seed", "to": "k::c::register", "args": ["k::b::X"]});
    let all = [
        module("k::a", &[], &["k::Tr"], &[]),
        cast.clone(),
        function.clone(),
        call,
        target(),
    ];
    assert_eq!(verdict(&facts(&all), &Mode::Rta), "kept");
    let without = [
        module("k::a", &[], &["k::Tr"], &[]),
        cast,
        function,
        target(),
    ];
    assert_eq!(verdict(&facts(&without), &Mode::Rta), "excluded");
}

#[test]
fn an_instance_flows_over_the_edges_of_generic_callers_and_into_trait_items() {
    let (f, g) = ("k::c::outer", "k::c::inner");
    let fns = [
        json!({"k": "fn", "f": f, "m": "k::c", "implements": null}),
        json!({"k": "fn", "f": g, "m": "k::a", "implements": "lib_ext::Item"}),
    ];
    let seed = json!({"k": "seed", "to": f, "args": ["k::b::X"]});
    let edge = json!({"k": "edge", "from": f, "to": "lib_ext::Item", "args": []});
    let all = [
        module("k::a", &[], &[], &[]),
        fns[0].clone(),
        fns[1].clone(),
        seed,
        edge,
        target(),
    ];
    assert_eq!(verdict(&facts(&all), &Mode::Rta), "kept");
}

#[test]
fn a_type_that_reaches_code_outside_the_workspace_is_coerced_there_h2() {
    let escape = json!({"k": "seed", "to": "<foreign>", "args": ["k::b::X"]});
    let implements = imp("k::c", Some("k::Tr"), &["k::b::X"], &[]);
    let holds_dyn = module("k::a", &[], &["k::Tr"], &[]);
    assert_eq!(
        verdict(
            &facts(&[holds_dyn.clone(), escape.clone(), implements, target()]),
            &Mode::Rta
        ),
        "kept"
    );
    let not_an_implementer = facts(&[holds_dyn, escape, target()]);
    assert_eq!(verdict(&not_an_implementer, &Mode::Rta), "excluded");
}

#[test]
fn the_associated_type_of_a_reached_impl_is_reached_h3() {
    let via = imp("k::c", Some("k::Tr"), &["k::c::W"], &["k::b::X"]);
    assert_eq!(
        verdict(
            &facts(&[
                module("k::a", &["k::c::W"], &[], &[]),
                via.clone(),
                target()
            ]),
            &Mode::Rta
        ),
        "kept"
    );
    assert_eq!(
        verdict(
            &facts(&[module("k::a", &[], &[], &[]), via, target()]),
            &Mode::Rta
        ),
        "excluded"
    );
}

#[test]
fn a_hidden_type_of_an_opaque_type_or_a_coroutine_is_reached_and_so_is_a_nested_one() {
    let outer = json!({"k": "opaque", "d": "k::c::outer", "hidden": [], "dyn": [], "opaque": ["k::c::inner"]});
    let inner =
        json!({"k": "opaque", "d": "k::c::inner", "hidden": ["k::b::X"], "dyn": [], "opaque": []});
    let all = [
        module("k::a", &[], &[], &["k::c::outer"]),
        outer.clone(),
        inner.clone(),
        target(),
    ];
    assert_eq!(verdict(&facts(&all), &Mode::Rta), "kept");
    assert_eq!(
        verdict(
            &facts(&[module("k::a", &[], &[], &[]), outer, inner, target()]),
            &Mode::Rta
        ),
        "excluded"
    );
}

#[test]
fn an_upcast_keeps_what_was_coerced_to_the_sub_trait() {
    let sub =
        json!({"k": "coerce", "tr": "k::Sub", "src": ["k::b::X"], "src_dyn": [], "param_in": []});
    let up =
        json!({"k": "coerce", "tr": "k::Super", "src": [], "src_dyn": ["k::Sub"], "param_in": []});
    let holds = module("k::a", &[], &["k::Super"], &[]);
    assert_eq!(
        verdict(
            &facts(&[holds.clone(), sub.clone(), up, target()]),
            &Mode::Rta
        ),
        "kept"
    );
    assert_eq!(
        verdict(&facts(&[holds, sub, target()]), &Mode::Rta),
        "excluded"
    );
}

#[test]
fn a_directory_of_units_is_read_and_a_merged_test_unit_adds_nothing() {
    let dir = std::env::temp_dir().join(format!("archkeel-reach-{}", std::process::id()));
    std::fs::create_dir_all(&dir).unwrap();
    std::fs::write(
        dir.join("u-1.jsonl"),
        file(&[module("k::a", &["k::b::X"], &[], &[]), target()], &[]),
    )
    .unwrap();
    std::fs::write(
        dir.join("u-1-test.jsonl"),
        "{\"k\":\"build\"}\n{\"k\":\"str\",\"v\":[]}\n{\"k\":\"end\",\"lines\":2}\n",
    )
    .unwrap();
    let loaded = Facts::load_dir(&dir).unwrap();
    assert_eq!(verdict(&loaded, &Mode::Rta), "kept");
    std::fs::remove_dir_all(&dir).unwrap();
}

#[test]
fn the_class_hierarchy_keeps_an_implementer_that_nothing_coerces_and_a_blanket_impl_keeps_all() {
    let holds = module("k::a", &[], &["k::Tr"], &[]);
    let implementer = imp("k::c", Some("k::Tr"), &["k::b::X"], &[]);
    let nobody = facts(&[holds.clone(), implementer, target()]);
    assert_eq!(verdict(&nobody, &Mode::Rta), "excluded");
    assert_eq!(verdict(&nobody, &Mode::Cha), "kept");
    let other = imp("k::c", Some("k::Other"), &["k::b::X"], &[]);
    assert_eq!(
        verdict(&facts(&[holds.clone(), other, target()]), &Mode::Cha),
        "excluded"
    );
    let blanket = imp("k::c", Some("k::Tr"), &[], &[]);
    let mentioned = module("k::c", &["k::b::X"], &[], &[]);
    assert_eq!(
        verdict(&facts(&[holds, blanket, mentioned, target()]), &Mode::Cha),
        "kept"
    );
}

#[test]
fn the_filter_gives_the_same_answers_whatever_the_order_of_the_questions() {
    let all = [
        module("k::a", &["k::b::X"], &[], &[]),
        module("k::c", &["k::c::Y"], &[], &[]),
        json!({"k": "coerce", "tr": "k::Tr", "src": ["k::b::X"], "src_dyn": [], "param_in": []}),
        target(),
    ];
    let loaded = [facts(&all)];
    let known = known();
    let pairs = [
        ("native.k.a", "native.k.b"),
        ("native.k.c", "native.k.b"),
        ("native.k.b", "native.k.a"),
    ];
    let forward = Filter::new(&loaded, &known);
    let answers: Vec<bool> = pairs.iter().map(|(a, b)| forward.excluded(a, b)).collect();
    let backward = Filter::new(&loaded, &known);
    let mut reversed: Vec<bool> = pairs
        .iter()
        .rev()
        .map(|(a, b)| backward.excluded(a, b))
        .collect();
    reversed.reverse();
    assert_eq!(answers, reversed);
    assert_eq!(answers, [false, true, false]);
    assert!(!Filter::new(&[], &known).excluded("native.k.a", "native.k.b"));
}

fn decided(scan: &[&str], all: &Facts, pair: (&str, &str)) -> &'static str {
    let scan: BTreeSet<String> = scan.iter().map(|m| m.to_string()).collect();
    let reach = Reach::new(all, &scan);
    match reach.decide(pair, &Mode::Rta, &mut BTreeMap::new()) {
        Verdict::Excluded => "excluded",
        Verdict::Kept(Cause::Reached) => "kept",
        Verdict::Kept(_) => "other",
    }
}

const BIN_SCAN: [&str; 4] = [
    "native.k",
    "native.k.bin_k",
    "native.k.bin_k.a",
    "native.k.bin_k.b",
];

#[test]
fn a_module_of_a_bin_target_is_decided_under_the_bin_module_not_the_library_root() {
    // The facts name `k::a`; the scan names the module of `main.rs` `native.k.bin_k.a` (`crates.rs`).
    let pair = ("native.k.bin_k.a", "native.k.bin_k.b");
    let reads = [module("k::a", &["k::b::X"], &[], &[]), target()];
    assert_eq!(
        decided(&BIN_SCAN, &facts_of(&[(&reads, &["bin"])]), pair),
        "kept"
    );
    let control = [module("k::a", &["k::a::Y"], &[], &[]), target()];
    assert_eq!(
        decided(&BIN_SCAN, &facts_of(&[(&control, &["bin"])]), pair),
        "excluded"
    );
}

#[test]
fn an_inline_module_of_the_library_keeps_its_facts_beside_a_bin_target() {
    // `k::inner` is an inline module of the library root: it has no scan module, the bin target must not take it.
    let scan = ["native.k", "native.k.b", "native.k.bin_k"];
    let library = [module("k::inner", &["k::b::X"], &[], &[]), target()];
    let bin = [module("k", &[], &[], &[])];
    let all = facts_of(&[(&library, &["lib"]), (&bin, &["bin"])]);
    assert_eq!(decided(&scan, &all, ("native.k", "native.k.b")), "kept");
}
